# graphify v8 and the ranked-search landscape, August 2026

- **Study for**: `../../2026-08-26-glean-brief.md` — question 13 (the
  landscape leg). Awareness, not imitation: the memo positions `glean`
  against these systems; it does not copy them.
- **Date**: 2026-08-26
- **Sources**: refreshed reference clones under `~/Git/Repos` (read-only;
  described and cited, never copied) — graphify `v8` @ `43d54ac`
  (0.9.50, 2026-08-25, Graphify-Labs/graphify, Apache-2.0), gbrain @
  `872c3d6`, HippoRAG @ `2f52a86`, LightRAG @ `812f2d5d`, graphrag @
  `f40e9a2`, cognee @ `690c0ec02`, graphiti @ `993e081`, letta @
  `4511fa0bc`, mem0 @ `39bc023`, memori @ `a7bf568`, MemOS @ `9119efe5`,
  zoekt @ `a9206004`; public docs and posts by URL in *Sources* at the end.
  Prior memos this refreshes: `../../2026-06-11-graphify-success-playbook.md`,
  `../../2026-04-20-graphify-and-lightrag.md`,
  `../../2026-07-21-gbrain-analysis.md`.

## Question

For each system that an agent-facing search product will be compared to
in August 2026: what does it actually do for retrieval and ranking today
(candidate generation, fusion arithmetic, signals, cross-collection
merge), what changed since our last memo on it, and is there any idea
worth stealing for `glean` — fused vector + BM25 ranking inside the SQL
engine with glob scoping, centrality and read-derived signals, top-*n*
entries with query-biased previews, and an honest cross-mount merge?

## 1. graphify (v8, 0.9.50)

**What it is now.** A Python library plus a skill file installed into
~20 coding assistants that turns a directory into a NetworkX graph
(`graphify-out/graph.json`, `graph.html`, `GRAPH_REPORT.md`) via
tree-sitter AST extraction for 36 languages and an LLM semantic pass for
docs/PDFs/images; queried by `graphify query|path|explain|affected` and
an MCP server (`serve.py`: `query_graph`, `get_node`, `get_neighbors`,
`get_community`, `god_nodes`, `graph_stats`, `shortest_path`, plus PR
triage tools). Since June it moved to the `Graphify-Labs/graphify` org
(2026-07-18, `4f9752c`), relicensed MIT → Apache-2.0 (2026-07-22,
`ba7f9ea`; `NOTICE` keeps the MIT text for pre-relicense contributions),
took YC S26 (founder Safi Shamsi, team of 2, London), and launched a
hosted "always-on" product. The YC page's one-liner is **"On-device
knowledge graph engine for enterprises"**, claiming 105K+ stars, ~5M
downloads, 6,000+ platform signups, and production users (Rootly,
Geotab, Tweddle Group, Superagent); the pitch adds "formal verification
of code changes" across repos and fully air-gapped deployment. The README
now carries a "graphify Enterprise" section ("the always-on layer built
on top of graphify … meetings, files, docs, and code, updating
continuously in the background") and an early-access login at
`app.graphify.com`. The blog post (2026-07-01) keeps the slogan "Query,
don't grep" and the on-device promise ("Your code never leaves your
machine unless you point Graphify at a hosted model").

**How it retrieves.** `graphify query "<question>"` is *lexical seed
selection on node labels followed by bounded graph traversal*
(`graphify/serve.py:1187` `_query_graph_text`). Verified: the README says
"Not a vector index. No embeddings, no vector store" (README.md:34) and
`docs/how-it-works.md:30` says the LLM's `semantically_similar_to` edges
"are the similarity signal — there's no separate embedding step or vector
database"; a grep of the package finds no embedding, BM25, or vector code.
The path is:

1. `_query_terms` (`serve.py:262`) tokenizes on `\w+`, segments Chinese,
   and drops a multilingual stopword list, falling back to the raw terms
   if everything was a stopword.
2. `_compute_idf` (`serve.py:290`) computes `log(1 + N/(1+df))` per term
   over **node labels** (df = nodes whose folded label contains the term
   as a substring), cached on the graph object.
3. A character-trigram posting index over each node's label, label
   tokens, id, and source path (`_node_search_text`, `_get_trigram_index`,
   `_trigram_candidates`, `serve.py:319-430`) narrows candidates; it
   bails to a full scan when a needle's rarest trigram covers >10% of
   nodes (`guard_frac`), so results are byte-identical either way.
4. `_score_query` (`serve.py:461`) scores each candidate with fixed
   tiers: exact label match `1000·idf`, prefix `100·idf`, substring
   `1·idf`, source-path substring `0.5·idf`, and a whole-query tier
   (`10×` the exact/prefix bonus, weighted by the rarest term's IDF).
   Exact/prefix contributions are then multiplied by *squared term
   coverage* `(matched/n_terms)²` so one generic exact match cannot bury
   a node matching several terms (#1602). Ties break by shorter label,
   then node id.
5. `_pick_seeds` (`serve.py:655`) takes up to 3 seeds, stopping when the
   score falls below 20% of the top score (`gap_ratio`), de-duplicating by
   normalized label so a hundred `GET` handlers yield one seed, and then
   **guarantees one seed per query term** (the per-term winner computed
   in the same pass), minus relational-intent verbs ("calls", "uses" —
   `_RELATIONAL_INTENT_TERMS`, `serve.py:766`) which are demoted so they
   cannot seat a decoy root.
6. `_bfs`/`_dfs` (`serve.py:922-982`) expand from the seeds to `depth=3`
   (BFS default) over a context-filtered view (edge `context` in
   {call, import, field, parameter_type, return_type, generic_arg},
   inferred from the question's verbs or passed explicitly), **never
   expanding through hubs** whose degree is at or above the p99 of the
   degree distribution (floored at 50) unless the hub is itself a seed.
   `_complete_induced_edges` then adds every edge among visited nodes so
   the output is the induced subgraph, not the traversal tree.

**How it ranks/fuses.** There is no fusion of independent ranked lists:
the lexical tier score picks seeds, then traversal *replaces* ranking.
The rendered answer (`_subgraph_to_text`, `serve.py:985`) orders seeds
first, then remaining nodes by **hop distance from the seeds, then degree
descending, then id**, and cuts at a ~3-chars-per-token budget (default
2000 tokens) with the seed block never cut. Truncation is announced at
the top of the output with the count of cut nodes and narrowing hints;
a complete answer that overflows the budget is labelled "complete answer
over budget" rather than truncated (0.9.46, #2784). The skill adds a
step the binary does not: "constrained query expansion" — the host agent
extracts the graph's label vocabulary to `.vocab.txt` and rewrites the
question using only tokens from that list (up to 12), because the matcher
has "no stemming, no synonyms, no cross-language match"
(`graphify/skills/kilo/references/query.md`, Step 0).

**Signals used.** Label/id/path substring tiers; IDF over labels; term
coverage; graph degree (as a hub *penalty* in traversal and a *tie-break*
in ordering and community labelling — `cluster.py:86`
`label_communities_by_hub`); hop distance; edge `context`; confidence
tags rendered but not scored. Betweenness centrality appears only in
analysis (`analyze.py:358,460` — edge betweenness for "surprising
connections" without communities; sampled node betweenness `k` for
suggested questions). **No PageRank, no eigenvector/Katz, no embeddings,
no recency, no access counts.** Community detection is Leiden
(graspologic) with Louvain fallback (`cluster.py:22`), with an optional
`--exclude-hubs <percentile>` that partitions without super-hubs and
reattaches them by neighbour majority vote (`cluster.py:137-206`).
A **feedback loop exists but is deliberately kept out of ranking**:
`graphify save-result --outcome useful|dead_end|corrected` files Q&A as
markdown into `graphify-out/memory/` (`ingest.py:274`), `graphify
reflect` aggregates those into signed, half-life-decayed (30-day) node
scores needing ≥2 corroborating results to become "preferred"
(`reflect.py:1-60,275-346`), and the verdicts render as a
`learning=` suffix on query output from a sidecar
(`serve.py:62,992-1036`). The 0.9.3 changelog states why it stops there:
"Letting verdicts influence query traversal is deliberately deferred (it
needs propensity correction + exploration to avoid a self-reinforcing
feedback loop)" (CHANGELOG.md, 0.9.3, 2026-06-30). That is the brief's
gap 5 (click/position bias) named by a competitor.

**Cross-collection story.** Two mechanisms, both offline composition:
`graphify merge-graphs` composes several repos' `graph.json` files with
`<repo>::` id prefixes, offsets community ids per input (0.9.50, #3014),
and links type declarations shared across repos with `same_type_as`
edges (0.9.49, #3007); `graphify global` maintains
`~/.graphify/global-graph.json` as a union across tracked repos
(`global_graph.py:11`). A query runs against whichever single graph file
is opened — the answer header now names the graph and its node count
because querying the wrong corpus was a reported failure (0.9.47,
#2789). There is no per-collection ranking to merge, so no merge problem.

**What changed since our last memo (0.8.35, June).** ~900 commits and 60
releases, still overwhelmingly extractor fixes (per-language resolution,
shadowing, id stability) and platform glue. On the query path
specifically: single-pass scoring with per-term seed metadata (0.9.19,
#1889); trigram candidate prefilter (0.9.4); coverage-squared scaling
(#1602); per-label seed dedup (#1766); multilingual stopwords (#1900);
relational-verb seed demotion (#2507); induced-subgraph completion
(#2323); honest over-budget notice (#2784); graph-name header (#2789);
work-memory sidecar + `reflect` (0.9.3); opt-in *strict* PreToolUse hook
that **denies** the first raw source read of a session with a redirect
to `graphify query`, then downgrades to a nudge (0.9.19); query log made
opt-in (#1797). Product side: org move, Apache relicense, YC S26,
`graphify Enterprise` waitlist, Postgres/SCIP/Google Workspace/MCP-server
introspection as corpus sources, PR-impact MCP tools, an RFC for
deterministic file-level node summaries (`docs/node-summaries-rfc.md`).
Star count went from ~63K (Augment's write-up) to 105K+ (YC page).

**Worth stealing / not.**
- *Steal:* the hub-suppression rule (p99-degree, floor 50, seeds exempt)
  as the shape of "degree is a penalty in expansion, a tie-break in
  ordering" — for `glean`'s graph signal, a high-degree file is a prior,
  not a reason to flood the neighbourhood. Already noted in June; still
  the only ranking idea in the codebase.
- *Steal:* the two-tier truncation honesty (top-of-output notice with the
  cut count and a narrowing hint, and "complete but over budget" as a
  distinct state) — maps onto glean's warning-severity envelope records.
- *Steal the caution:* their explicit refusal to feed outcome verdicts
  back into traversal without propensity correction is the right reading
  of the ULTR literature for the read-metrics requirement.
- *Not:* the retrieval model. Substring tiers over labels with hand-set
  1000/100/1 bonuses, IDF computed on labels, and an agent-side vocabulary
  rewrite are a workaround for having no lexical index over content and
  no embeddings; the skill's Step 0 exists because the engine cannot
  match "authentication" to `Guardian`. `glean`'s BM25 + vector legs over
  chunk content make the whole tier system unnecessary.
- *Not:* the artifact model. A static JSON graph re-read per query is what
  lets them stay index-free; vfs's live database is the opposite bet and
  the reason fusion can happen in one statement.

## 2. gbrain (872c3d6, v0.46.30.0)

**What it is now.** Garry Tan's TypeScript/Bun agent-memory system over
Postgres/PGLite; the July memo's picture (five-arm hybrid, RRF, boost
tower, cross-encoder, autocut, CI eval gate) still holds, with a month of
knob work on top. History was flattened on 2026-07-21 (`3cc34c9`), so
"since July" is dated from `CHANGELOG.md`.

**How it retrieves.** Each arm is its own SQL round-trip; fusion is
client-side. *Chunk FTS*: `ts_rank(search_vector, websearch_to_tsquery)`
times a source-prefix CASE prior, pooled at 3×limit chunks and collapsed
to one row per `(source_id, slug)` by a shared `DISTINCT ON` CTE
(`src/core/postgres-engine.ts:1502-1506`, `src/core/search/sql-ranking.ts:222-262`);
zero rows retries with OR-joined terms; CJK routes to ILIKE/bigram.
**Not BM25** — `docs/architecture/RETRIEVAL.md:8` says BM25 but the SQL is
`ts_rank`, and `src/core/search/mode.ts:80-90` admits the no-IDF noise.
*Page-title FTS*: `ts_rank_cd` at page grain, title weight A
(`postgres-engine.ts:1658-1681`). *Vector*: inner CTE `ORDER BY col <=> $1`
(pure distance so HNSW applies), inner limit
`min(offset + max(5·limit, 100), 1000)`, with
`set_config('hnsw.ef_search', clamp(innerLimit, 40, 1000), true)` per
transaction and a bounded ×4/≤3 escalation when the page set is short
(`:1920, :2013-2095`; `src/core/vector-index.ts:47-66`). *Relational*:
regex-parsed relational queries → seed pages → `WITH RECURSIVE` walk over
`links`, depth ≤3, limit ≤200, `ORDER BY hop, edge_count DESC`, pinned to
the seed's source (`:3544-3620`). *Image vectors*: same path over
`embedding_image`/`embedding_multimodal`. Each arm is asked for
`min(max(2·limit, 50, offset+limit), 100)` candidates
(`src/core/search/hybrid.ts:70-78, 1201-1204`).

**How it ranks/fuses.** RRF `Σ 1/(k_list + rank)` with **k = 60 divided
by an intent weight** per list (entity 1.15/1.0, event 1.20/0.95,
concept 0.9/1.2; `src/core/search/intent-weights.ts:66-123`), normalized
by the max, then blended `0.7·normRRF + 0.3·cosine` (`hybrid.ts:2933`).
Then the multiplicative tower, every step fail-open and floor-gated
(`computeFloorThreshold`, `:296`): backlinks `1+0.05·ln(1+n)`, salience
`1+k·ln(1+s)`, per-prefix hyperbolic recency, chronicle-type ×1.15/1.25
on temporal queries, title-phrase ×1.25, graph adjacency ×1.05/×1.10,
session demote ×0.95, alias ×1.05, supersede ×0.5, exact slug/title
×1.25/1.10. Four-layer dedup, cross-encoder rerank (Voyage `rerank-2.5`
for new installs; 5 s timeout, fail-open; `mode.ts:400-466`), an
*exact-lookup identity tier* that injects a slug/title hit at rank 1
regardless of scoring (`src/core/search/exact-lookup.ts:184-208`), and
autocut on reranker scores only (jump ratio 0.2, min keep 1, no-op when
top < 0.35; `autocut.ts:56-60`). Three mode bundles (conservative 10 /
balanced 25 / tokenmax 50). Every knob change bumps a cache-key version —
26 so far (`mode.ts:952`).

**Signals used.** ts_rank/ts_rank_cd, cosine, RRF rank, source prior,
intent class, backlink count, emotional weight + take count, effective
date, page type, title match, adjacency, session prefix, aliases,
supersedes edges, reranker score. **No read/access signal affects
ranking**: `pages.last_retrieved_at` is written but consumed only as a
stale-page signal for the dream cycle (`src/core/last-retrieved.ts:1-11`);
`query_cache.hit_count` is cache instrumentation. **No PageRank or
centrality**; degree enters only as the bounded backlink log-boost and a
≥2-inbound-in-top-K hub bump.

**Cross-collection story.** "Sources" are tenants in one database; a
federated caller passes `sourceIds` and every arm pushes
`p.source_id = ANY($n::text[])` into its inner CTE — one statement per
arm, fused client-side (`postgres-engine.ts:1461-1471, 1959-1971`).
Relational traversal never crosses a source. "Brains" are separate
databases and cross-brain search is explicitly the *agent's* job, not SQL
federation (`docs/architecture/brains-and-sources.md:181-225`). There is
no answer to heterogeneous embedders across brains.

**What changed since the July memo.** Recency-decay honoured on the
hybrid path (07-24 `31dca68`); quarantine lane for unverified stubs
(07-27 `56aac51`); compiled-truth boost restricted to `detail='low'` —
the old predicate had made default search compiled-truth-only (07-28
`85286a5`); fail-loud retrieval with a `degraded[]` trail and
`allSettled` salvage of the embed/vector fan-out (08-14 `6a905a1`);
ZeroEntropy → Voyage reranker default (08-15 `cc3e284`); `concept`
intent, vector-pool escalation, autocut weak-top floor (08-17 `afe9236`);
supersede ×0.5 and `autocut_min_keep` (08-19); pre-fusion pool floor 50,
64k-char/256-term query bound, keyword-arm fail-open (08-21 `055ac6c`);
exact-lookup identity tier, CRAG confidence grade, private-visibility
predicate in every arm, guaranteed page-1 relational slot (08-21
`67e7e8a`); chunkless rows through the cosine blend with cosine=0 (08-24
`492b552`).

**Worth stealing / not.**
- *Steal:* pure-distance inner CTE plus transaction-local `ef_search`
  sized to the candidate LIMIT — HNSW returns at most `ef_search` rows,
  so an unsized LIMIT is silently unreachable. This is a per-dialect
  fact for the engine matrix study.
- *Steal:* in-SQL per-entity max-pool (`DISTINCT ON (source, slug)` with
  a deterministic tie-break) before the user LIMIT, one builder shared by
  every arm — the SQL-side MaxP the brief's gap 2 asks about.
- *Steal:* the identity floor — an exact path/title query lands at rank 1
  without consulting the ranker. A `glean` for a file the user can name
  must never lose to content noise (the July "title arm" point, now
  hardened into a tier).
- *Steal:* the `degraded[]` trail — every arm that failed or fell back is
  named in the response. This is gap 9 (result honesty) implemented.
- *Skip:* the client-side multiplicative boost tower over normalized RRF
  (any boost ≥2 beats rank 1 vs rank 60; every knob forces a cache-key
  bump) and `ts_rank` as the lexical scorer. Fusion belongs in one
  statement and lexical ranking needs document frequency.

## 3. HippoRAG (2f52a86, 2.0.0a5)

**What it is now.** HippoRAG 2 — an OpenIE-built graph of phrase nodes
and passage nodes joined by fact, passage, and synonymy edges, over which
personalized PageRank ranks passages (`src/hipporag/HippoRAG.py`).

**How it retrieves.** `retrieve()` (`HippoRAG.py:691-781`): (1) dot
product of the query embedding against *all* fact-triple embeddings in
memory, min-max normalized (`:1879-1915`); (2) the top `linking_top_k=5`
facts go through the "recognition memory" filter — a DSPy few-shot LLM
prompt returning the facts to keep (`rerank.py:14-127`), fuzzy-matched
back with `difflib`; (3) zero surviving facts → **pure dense passage
retrieval fallback** (`:749-751`); otherwise
`graph_search_with_fact_entities` (`:1995-2108`). Seeds are therefore
fact-embedding hits gated by an LLM, not entity-embedding hits; entity
embeddings only build synonymy edges at index time (kNN top 2047, cosine
≥ 0.8).

**How it ranks/fuses.** For each kept fact, subject and object phrase
nodes receive the fact score **divided by the number of chunks the
entity occurs in** (`:2052` — an IDF-like damping of hub entities),
averaged over occurrences; `get_top_k_weights` zeros all but the top
`link_top_k` phrase weights (`:1957-1993`). Every passage node gets
`dpr_score × passage_node_weight` with `passage_node_weight = 0.05`
(`:2084`; `config_utils.py:91-94`). Reset vector = phrase weights +
passage weights; igraph `personalized_pagerank(damping=0.5,
directed=False, weights='weight', implementation='prpack')`
(`:2164-2205`). Passage nodes' PPR mass is argsorted; top
`retrieval_top_k=200` returned. Edge weights: fact edge = co-occurrence
count across chunks, passage edge = 1.0, synonymy = cosine, merged as
`max(Σ fact counts, 1.0, synonym)` (`:1576`). No post-PPR reranker; DPR
enters only through the teleport prior.

**Signals used.** Dense query→fact, dense query→passage (as a 0.05
prior), LLM fact filter, graph structure via PPR with co-occurrence
weights, inverse chunk frequency on seeds. No lexical, recency, or
access signals.

**Cross-collection story.** Three namespaced embedding stores (entity,
fact, chunk; parquet default, Qdrant/Chroma/Milvus optional) are
**bulk-loaded into numpy at retrieval** (`:1770-1773`); the vector store
is persistence only. No cross-store merge beyond the reset vector.

**What changed since mid-2026.** Eight commits in 2026; a re-squash on
07-12 and a +940-line rework on 08-23 adding an `index_manifest.json`
that binds vectors and OpenIE output to embedding/LLM identity with
`StateConsistencyError` refusals (`:307-404`), `delete()` with
source-aware edge metadata, explicit `directed=False`. A CWE-95 fix
replaced `eval` in the reranker (07-28). No ranking-formula change.

**Worth stealing / not.**
- *Steal:* the seed-IDF trick — dividing a hub's seed weight by its
  chunk count is a `1/COUNT(chunk)` normalization expressible in SQL,
  and it is the right shape for feeding degree-heavy centrality into a
  fusion without letting popular nodes swamp it.
- *Steal:* the explicit dense-only fallback when the graph leg yields
  nothing, and the index manifest that refuses a query embedded by the
  wrong model (gap 3, embedding identity, solved the blunt way).
- *Not:* whole-corpus in-memory PPR and full-matrix dot products; the
  0.05 passage prior is a hand-tuned constant that the harness (gap 8)
  would have to re-derive.

## 4. LightRAG, graphrag, cognee, graphiti

### 4.1 LightRAG (812f2d5d)

**What it is now.** Entity/relation KG with three vector collections
(entities, relationships, chunks), a graph store and a chunk KV; query
modes `local | global | hybrid | naive | mix | bypass`, default `mix`
(`lightrag/base.py:92-99`).

**How it retrieves.** `kg_query` (`lightrag/operate.py:4504-4738`) gets
LLM high/low-level keywords (cached; raw query becomes the ll keyword if
both are empty), then `_perform_kg_search` (`:5041-5260`) embeds
query/ll/hl in one batch and hits the entity vdb (`top_k=40`), the
relationship vdb, and for `mix` the chunk vdb directly (`chunk_top_k=20`);
every vdb call applies `cosine_better_than_threshold=0.2`. `naive` is
chunk-vdb only; `bypass` skips retrieval.

**How it ranks/fuses.** Entities keep vdb order, stamped `rank` = node
degree (`:5912-5923`); their 1-hop edges sort by `(edge_degree, weight)`
desc. Local and global lists are **merged round-robin with dedup**
(`:5193-5230`). Chunks derived from entities and from relations are
picked by `kg_chunk_pick_method=VECTOR` (cosine of the query against the
candidate chunks' stored vectors, taking
`related_chunk_number·len(entities)/2`) or `WEIGHT` (linear-gradient
polling by entity position), then `_merge_all_chunks` (`:5477-5583`)
does a **three-way round-robin: vector chunk, entity chunk, relation
chunk**. `process_chunks_unified` (`utils.py:5952-6040`) reranks via
`rerank_model_func` when `enable_rerank` (default true), drops
`rerank_score < 0.0`, slices to `chunk_top_k`, and token-truncates to
`max_total_tokens` minus prompt overheads. **Without a reranker there is
no score fusion at all — order is the round-robin order.**

**Signals used.** Vector similarity ×3, LLM keywords, node degree and
edge degree+weight (for prompt ordering only), chunk occurrence count,
external reranker. **No BM25 leg** — Neo4j's fulltext index serves only
the WebUI label search (`kg/neo4j_impl.py:1913-1964`). No recency.

**Cross-collection story.** Three vdbs + graph + KV, merged positionally;
`chunk_tracking` records source `C/E/R` and frequency for diagnostics.

**What changed since mid-2026.** ~1,700 commits, almost none on ranking:
content-heading backfill into chunk context (06-06), BFS tie-break by
degree then label (Aug), Milvus paging, rerank overlap validation, redo-log
durability. Round-robin merge, VECTOR pick, min-rerank filter all
predate 2026.

**Worth stealing / not.** *Steal* round-robin-with-dedup as the
score-free fusion for heterogeneous legs — `ROW_NUMBER() OVER (PARTITION
BY leg)` then `ORDER BY rn, leg_priority` — it is what a cross-mount
merge degrades to when scores are incomparable and no reranker is
available. *Not* the multi-round-trip fan-out (40 entities → all their
chunks → re-embed compare); one join does that.

### 4.2 Microsoft GraphRAG (f40e9a2, v3.1.2)

**What it is now.** Four query engines — local, global, DRIFT, basic —
over parquet-loaded entities/relationships/community reports/text units
plus `graphrag-vectors`.

**How it retrieves.** *Local*: `map_query_to_entities`
(`context_builder/entity_extraction.py:44-96`) does vector kNN on entity
description embeddings with `k = top_k_entities × oversample_scaler(2)`
then applies include/exclude lists; only the no-vector-store branch sorts
by `rank`. Defaults `top_k_entities=10`, `top_k_relationships=10`,
`text_unit_prop=0.5`, `community_prop=0.15`, `max_context_tokens=12000`
(`config/defaults.py:264-269`). *Global*: no vector step — community
reports at a level are shuffled and batched to the token budget, or
filtered by `DynamicCommunitySelection` (LLM rating ≥ 1, BFS down the
hierarchy). *DRIFT*: cosine of query vs report embeddings, top 20,
primer decomposes into follow-ups, `n_depth=3` rounds of local search.
*Basic*: text-unit kNN.

**How it ranks/fuses.** Local: text units are gathered per selected
entity and sorted by `(entity_order, −num_relationships)` where
`num_relationships` counts the entity's relationships attached to that
unit (`local_search/mixed_context.py:319-342`) — *by selected entity
then relationship density*, not by how many selected entities touch the
unit. Communities sort by `(matches, rank)` = selected entities inside,
then LLM rating. Relationships: in-network first by `rank`, then
out-network by `(links, rank)`. Everything is token-budget fill with
`break`. Global reduce drops score-0 key points and sorts by the LLM's
0–100 score.

**Signals used.** Entity `rank` = degree; relationship `rank` =
`combined_degree`; community `rank` = LLM rating; community `occurrence`
= max-normalized text-unit count of matched entities. Vector similarity
only for lookup. **No lexical leg anywhere** (the Azure adapter sends
`vector_queries` only). No recency or access.

**Cross-collection story.** One vector collection per embedded field;
each engine hits one collection then joins in-memory dataframes; fusion
is by proportional token budgets, never by score.

**What changed since mid-2026.** Query directory touched only by a
docs spelling pass (08-14) and a 25-line cleanup (08-24). 3.1.x
changelog is deps, Cosmos table provider, vector-size validation.

**Worth stealing / not.** *Steal* oversample-then-filter (`k×2`) for a
vector leg that carries exclusions (trash, permissions, scope), and
precomputed `degree`/`combined_degree` as stored rank columns. *Not*
proportional token-budget packing — prompt assembly, not retrieval
ranking.

### 4.3 cognee (690c0ec02, v1.5.3)

**What it is now.** A multi-store memory layer whose `search()` is a
`SearchType` enum dispatched to one retriever class per mode
(`cognee/modules/search/methods/get_search_type_retriever_instance.py:96-345`),
fanned out per dataset with no cross-dataset fusion
(`search/methods/search.py:339-367`).

**How it retrieves.** CHUNKS → vector collection `DocumentChunk_text`;
SUMMARIES → `TextSummary_text`; TRIPLET_COMPLETION → `Triplet_text`;
GRAPH_COMPLETION (and its COT/decomposition variants) →
`brute_force_triplet_search`: concurrent vector search over
`Entity_name, TextSummary_text, EntityType_name, DocumentChunk_text,
DltRow_text` plus `EdgeType_relationship_name` at
`wide_search_top_k=100` each (`retrieval/utils/brute_force_triplet_search.py:293-311`),
then the graph DB is projected into an in-memory `CogneeGraph` (full,
id-filtered, or k-hop around the vector seeds); HYBRID_COMPLETION →
chunks (2k) + summaries (k) + entities + edges, then 1-hop neighbours;
**CHUNKS_LEXICAL → in-process Okapi BM25 over every `DocumentChunk` node
loaded from the graph engine** (`retrieval/bm25_retriever.py:73-104`);
CYPHER/NATURAL_LANGUAGE → raw or LLM-generated Cypher; FEELING_LUCKY →
an LLM picks the mode.

**How it ranks/fuses.** No score normalization anywhere; adapters return
raw cosine distance (LanceDB `LanceDBAdapter.py:1004-1091`, pgvector
`PGVectorAdapter.py:535+`). `limit=None` means **full-collection scan**
(`LanceDBAdapter.py:1027-1028`), used by batch mode and node-scoped
GRAPH_COMPLETION. Cross-collection "merge" is identity overwrite: each
hit's distance is written onto the graph element with that id, later
collections overwriting earlier, unmatched elements at penalty 6.5
(`graph/cognee_graph/CogneeGraph.py:349-371`). Triplet score = Σ over
(node1, node2, edge) of `(2 − importance_weight)·distance`, blended with
feedback (`(1−f)·d/2 + f·(1−feedback_weight)`) and a personal factor,
`heapq.nsmallest(k)` (`CogneeGraph.py:417-505`). The hybrid chunk lane
does **RRF over vector rank and summary rank with
`k = max(30, min(60, 20 + 2·top_k))`**, times importance `0.75 + 0.5·w`,
sort by (score, rrf, best rank, id) (`retrieval/hybrid/ranking.py:22-69`).
A session two-lane merge (raw query vs conversational rewrite) puts items
present in both lists first and reserves ~1/3 for the secondary lane
(`utils/merge_results.py:68-118`).

**Signals used.** Cosine distance; LLM/user `importance_weight` (default
0.5, set at add time); `feedback_weight` — 1..5 ratings EMA'd with α=0.1
by memify (`tasks/memify/apply_feedback_weights.py:43-59`) — gated by
`feedback_influence` **defaulting to 0.0** (`base_config.py:26-28`);
per-user preference weights, off by default. Degree and PageRank only in
GRAPH_REPORT (`graph_report_retriever.py:253-268`). **`last_accessed` is
written (`utils/access_tracking.py:19-42,136-147`) but consumed only by
cleanup/activity, never ranking.** No lexical leg in any vector adapter;
no recency; no reranker model.

**Cross-collection story.** Per-collection top-k, no normalization, fused
only through graph-element identity in memory; datasets searched
independently and returned as separate results.

**What changed since mid-2026.** 95 retrieval commits: BM25 lexical mode
(06-08 `76a9253d6`), HybridRetriever (06-09 `65ed79aa5`), truth-subspace
reranking (06-25), GRAPH_REPORT (07-02), session two-lane merge (08-13
`335e326c9`), personalization (08-21 `c659c51cc`), per-type search
timings.

**Worth stealing / not.** *Steal* the shape of an EMA'd, bounded [0,1]
feedback weight as a multiplicative column, and the "present in both
lists first" agreement merge (a rank-agreement heuristic that is a
cheap prior for the cross-mount merge). *Not* whole-graph in-memory
projection and `limit=None` scans — the unbounded-statement pattern
vfs forbids.

### 4.4 graphiti (993e081, v0.29.3+)

**What it is now.** Zep's temporal knowledge graph; `search()` runs four
independent scopes — edges, nodes, episodes, communities — each a
configurable set of legs plus one reranker
(`graphiti_core/search/search_config.py:32-118`, `search.py:98-250`).

**How it retrieves.** Each leg asks for `2·limit` candidates (default
limit 10). *Fulltext*: `fulltext_query()` builds `group_id:"g" AND
(lucene_sanitize(q))`, skipping queries over 128 tokens
(`search_utils.py:85-113`); `lucene_sanitize` escapes specials *and the
letters O,R,N,T,A,D* to neutralize operators (`helpers.py:79-113`); no
fuzzing. Backends: Neo4j `db.index.fulltext.queryNodes/Relationships`
(Lucene BM25) over `node_name_and_summary`, `edge_name_and_fact`,
`episode_content`, `community_name` (`graph_queries.py:131-175`);
FalkorDB RediSearch with stopword-filtered OR-joined tokens; Kuzu
`QUERY_FTS_INDEX`; Neptune OpenSearch `multi_match` then a Cypher join by
id. *Vector*: in-DB cosine with `WHERE score > 0.6 ORDER BY score DESC
LIMIT` (`search_utils.py:406-424`); Neptune computes cosine in Python.
*BFS*: `(origin)-[:RELATES_TO|MENTIONS*1..depth]->` up to depth 3, origins
= supplied uuids or the other legs' hits (`:522-539`).

**How it ranks/fuses.** `rrf(results, rank_const=1)`: `Σ 1/(rank+1)`,
sorted, dropped below `reranker_min_score` (`search_utils.py:1764-1778`)
— **RRF with k = 1**, not 60. MMR: single-pass `λ·cos(q,c) + (λ−1)·max_j
sim(c,c_j)`, λ = 0.5 (combined recipes use λ = 1, i.e. pure similarity).
Cross-encoder: RRF shortlist capped at 2·limit, then
`cross_encoder.rank(query, facts)` (`search.py:396-411`). Node-distance:
RRF seed, one 1-hop query, score 1 if directly related to the centre
else ∞ — a two-bucket sort, not graph distance (`:1782-1841`).
Episode-mentions for nodes: RRF then `count(MENTIONS)` **sorted
ascending** (fewest mentions first; the comment says "shortest distance"
— looks like a copy-paste bug, `:1844-1882`); for edges, descending by
`len(edge.episodes)`. Final truncate to `limit`.

**Signals used.** Lucene/RediSearch BM25 (rank only), cosine with a 0.6
floor, BFS reachability, 1-hop adjacency, mention counts, cross-encoder.
Temporal `valid_at/invalid_at/created_at/expired_at` are **filters
compiled into the same WHERE** (`search_filters.py:120-273`), never
weights; no default expiry exclusion; no degree or PageRank.

**Cross-collection story.** One graph store; the four scopes run
concurrently and return four separate lists — `merge()` concatenates
(`search_config.py:132-160`). Backend differences are isolated in
per-driver `search_interface`/`build_fulltext_query` hooks
(`driver/driver.py:92-142`) — the closest analogue to vfs's
`DialectProfile`, and a confirmation that per-backend fulltext syntax is
the seam that must be owned.

**What changed since mid-2026.** Sixty commits, mostly CLA noise;
substantively the cross-encoder shortlist is now RRF-fused and capped at
2·limit instead of first-`limit` dict order (08-12 `d40da88`), BFS
direction preserved (`b0ec6d9`), FalkorDB fulltext stopword/backtick
handling, 0.29.3.

**Worth stealing / not.** *Steal* the declarative "legs + reranker"
recipe and the date predicates compiled into the leg's WHERE (trash and
version exclusion belong in the same place). *Skip* the rerankers as
implemented (1-hop only; the ascending-count bug) and single-pass MMR in
Python.

## 5. Agent memory: letta, mem0, memori, MemOS

**Headline for the read-metrics requirement (R1, gap 5).** None of the
four *open-source* codebases ranks on read or access counts. Three
record something access-shaped and never read it back for ranking
(letta's `files_agents.last_accessed_at`, cognee's `last_accessed`,
MemOS's `usage` list whose writer is now a docstring); memori's
`num_times` is a *write-side* re-extraction counter that shapes the
candidate pool; the only system that ranks on reads is mem0's
**closed platform** ("Memory Decay"), and its published shape is a
bounded multiplicative factor over an over-fetched pool. gbrain (§2) is
the same story: `last_retrieved_at` written, consumed only by the dream
cycle.

### 5.1 letta (4511fa0bc — archived)

**What it is now.** A landing-page stub: `87fd37aab` (2026-08-15)
deleted `letta/` and points at `letta-ai/letta-code` and the
`origin/archive` branch; the search code below was read via
`git show 87fd37aab^:<path>` (last search change 2026-03-25).

**How it retrieves.** Passages carry `text`, `tags`, and an `embedding`
zero-padded to pgvector `Vector(4096)` (`letta/orm/passage.py:21-40`,
`services/passage_manager.py:156-159`) with **no HNSW/IVFFlat index**.
Dispatch (`services/agent_manager.py:2416-2530`): archives on Turbopuffer
get hybrid; otherwise SQL — `ORDER BY embedding <=> q` with `created_at`
range filters and no threshold (`services/helpers/agent_manager_helper.py:1180-1258`);
the non-embedding path is `lower(text) LIKE '%q%'` (`:1258`). SQLite
orders by a Python cosine UDF — a full scan. Tags are post-filtered in
Python *after* LIMIT (`:2507-2527`, with a TODO). Turbopuffer modes:
`vector`, `fts` (BM25), `timestamp`, `hybrid` = ANN + BM25 multi-query
(`helpers/tpuf_client.py:791-894`).

**How it ranks/fuses.** `_reciprocal_rank_fusion` (`tpuf_client.py:1489-1559`):
**k = 60**, 1-based ranks, `0.5/(k+r_vec) + 0.5/(k+r_fts)`, an absent
list contributes 0; per-source ranks are surfaced to the agent as
`relevance: {rrf_score, vector_rank, fts_rank}` (`agent_manager.py:2655-2666`).
SQL path returns score 0.0. No reranker.

**Signals.** Vector; BM25 (Turbopuffer only); tags; date range.
**Access: no** — the only hits are `files_agents.last_accessed_at`
(per-agent file opens) and a schema field `block.last_accessed_at` with
no ORM column behind it.

**Cross-collection.** Multi-archive agents *raise* on vector search
(`agent_manager.py:2445-2446`). Messages have no embedding column; the
fallback is `ILIKE` over JSON with date filters dropped.

**What changed since mid-2026.** README/policy chores, then the archive.

**Worth stealing / not.** *Steal* per-leg ranks in the result metadata
(`vector_rank`, `fts_rank`) — the explain surface the ranker API should
expose. *Not* `LIKE '%q%'`, unindexed padded vectors, post-LIMIT filters.

### 5.2 mem0 (39bc023, OSS v2.0.19)

**What it is now.** v2.0.0 (2026-04-14) was a rewrite: hybrid
semantic + BM25 + entity retrieval, and **external graph stores
(Neo4j/Memgraph/Kuzu) removed** in favour of a built-in entity collection
(`docs/changelog/highlights.mdx:226-238`; no `graph_memory.py` remains).

**How it retrieves.** `Memory.search(query, top_k=20, filters,
threshold=0.1, rerank=False, explain=False, ...)` (`mem0/memory/main.py:1379-1391`);
`_search_vector_store` (`:1628-1700`) lemmatizes, extracts entities,
embeds; semantic search with `internal_limit = max(4·top_k, 60)`;
`keyword_search` over `text_lemmatized` at the same over-fetch; entity
boost via the entity collection; expired rows filtered by payload.
pgvector's lexical leg is `ts_rank_cd(to_tsvector('simple',
text_lemmatized)) @@ plainto_tsquery` (`mem0/vector_stores/pgvector.py:369-403`);
qdrant and elasticsearch also implement `keyword_search`; other stores
warn and go semantic-only.

**How it ranks/fuses.** `mem0/utils/scoring.py`: raw BM25 → logistic
sigmoid with query-length-adaptive `(midpoint, steepness)` (`:16-43`);
`ENTITY_BOOST_WEIGHT = 0.5`; `score_and_rank` (`:60-140`) gates on the
*semantic* score first, then `combined = min((semantic + bm25 +
entity)/max_possible, 1)`, sorts, cuts to top_k; `explain=True` returns
the breakdown. Optional cross-encoder/LLM reranker after.

**Signals.** Vector, sigmoid-BM25, entity-link boost, expiration filter.
No recency in scoring. **Access in OSS: no** — `decay=True` raises a
"platform-only" notice (`main.py:467-483`). **Platform: yes** —
`docs/platform/features/memory-decay.mdx:1-50` (2026-05-08): per-project
opt-in; every returned memory gets a fire-and-forget reinforcement
(history capped at 20 touches); a scaling factor **0.3×–1.5×** is
multiplied into the score at search time; the pool widens to
`max(3·top_k, 50)`; sort on the unclamped product, return clamped [0,1];
memories without history fall back to `event_date` then `updated_at`.

**Cross-collection.** One memory + one entity collection per store;
filters must carry a scope id. No cross-store fusion.

**What changed since mid-2026.** `explain` details, expiration and
`show_expired`, entity-boost weighting, platform-only notices, a docs
fix removing decay claims "that contradict the SDK" (`9e99eaa`).

**Worth stealing / not.** *Steal* the decay *shape*: a bounded
multiplicative factor over an over-fetched pool, never a filter, with a
fallback to modification time when there is no history — this is the
one published read-signal design and it maps to one column pair and an
`ORDER BY score × f(age, count)`. *Steal* semantic-threshold-before-
fusion as a gate. *Not* sigmoid-normalized BM25 with hand-tuned
midpoints — RRF avoids the calibration.

### 5.3 memori (a7bf568, v3.3.7)

**What it is now.** Python SDK over a Rust core with storage drivers for
sqlite/postgresql/mysql/oracle/oceanbase/mongodb
(`memori/storage/drivers/*`), local fastembed embeddings, and a cloud
mode.

**How it retrieves.** `memori_entity_fact` rows carry `content`,
`content_embedding BLOB`, `num_times`, `date_last_time`
(`memori/storage/migrations/_sqlite.py:124-145`). Recall pulls up to
1,000 embeddings for the entity `ORDER BY date_last_time DESC, num_times
DESC` (`drivers/sqlite/_driver.py:326-343`), then does **in-Python
cosine** over the pool (`memori/search/_core.py:43`), cuts to
`max(limit, min(N, max(10·limit, 50)))`, and fetches content by id. No
FTS5/tsvector/FULLTEXT anywhere; the lexical leg is an in-process BM25
(`memori/search/_lexical.py:74-124`), max-normalized.

**How it ranks/fuses.** `rank = w_cos·cosine + w_lex·bm25` with
`w_lex = 0.15` (0.30 for ≤2-token queries, clamped [0.05, 0.40]), cosine
tie-break, then `recall_relevance_threshold = 0.1`
(`_core.py:116-150`, `_lexical.py:126-150`).

**Signals.** Vector, BM25. **Access: not on the read path.** `num_times`
and `date_last_time` are bumped only by the fact upsert (`ON CONFLICT DO
UPDATE SET num_times = num_times + 1`, `_driver.py:257-277`) — "how many
times this fact was re-extracted" — and they *do* order the 1,000-row
candidate pool via `idx_memori_entity_fact_entity_id_freq`, so old,
rarely-restated facts fall out before scoring.

**Cross-collection.** Scoped by entity; one entity per recall.

**What changed since mid-2026.** 3.3.6 (05-27) moved embeddings to Rust
fastembed; `[Unreleased]` adds `recall()` validation.

**Worth stealing / not.** *Note* the honest trick — a write-side
frequency is transactional and free, a read-side counter costs a write
per search. *Not* "pull 1,000 rows, score in Python", nor its
interpolated unchunked `IN (...)` lists (`_driver.py:346-360`).

### 5.4 MemOS (9119efe5, v2.0.31)

**What it is now.** A tree/graph textual memory over Neo4j/PolarDB/Nebula
with Working/LongTerm/User tiers, a scheduler, and an API layer;
retrieval in `src/memos/memories/textual/tree_text_memory/retrieve/`.

**How it retrieves.** `Searcher.search → _parse_task → _retrieve_paths →
post_retrieve` (`retrieve/searcher.py:191-281`); `fast` mode skips the
LLM parse. Paths in a 5-worker pool: WorkingMemory = all activated nodes
`[:top_k]` with no ORDER BY; LongTerm and User each ask for `2·top_k`.
Hybrid recall (`recall.py:133-184`): graph leg (`key IN keys` ∪ tag
overlap ≥2), vector leg (max score per node across query vectors), BM25
leg (in-process `rank_bm25` over key+tags of **all** scope nodes),
fulltext (Neo4j stub returns `[]`; PolarDB `tsvector @@ to_tsquery` +
`ts_rank`, `graph_dbs/polardb.py:1789-1816`) — merged by **dict-on-id
union, no score fusion**.

**How it ranks/fuses.** Each path reranks its own candidates
(cosine × `level_weights` all 1.0, or an HTTP BGE cross-encoder with a
`(1+w)` metadata boost that is dead on the main path because the searcher
passes `search_filter=` and the reranker reads `search_priority`);
`post_retrieve` dedups by text keeping max and sorts the concatenation
by score with per-type quotas (`searcher.py:1149-1280`). No time decay.

**Signals.** Vector, key/tag match, BM25, cross-encoder. **Access: data
exists, no effect, writer disabled.** `usage: list[str]` on node metadata
is appended by `_update_usage_history` whose body now lives inside its
docstring (`searcher.py:1343-1368`; neutered at root commit `554bb98e`,
07-19); `dream/types.py:81-90` declares `last_hit_at, hit_count,
usefulness_score` with no writer ("intentionally left unimplemented").
The scheduler's `importance = 0.9·sorting + 0.05·keywords +
0.05·recording_count` (`mem_scheduler/schemas/monitor_schemas.py:211-262`)
only decides WorkingMemory/KV-cache activation, never LongTerm scores.

**Cross-collection.** `MOSCore.search` loops cubes and returns per-cube
buckets; the API's composite view extends lists, applies a relativity
threshold, 0.92-cosine dedup, and re-buckets (`api/handlers/search_handler.py:254-329`).

**What changed since mid-2026.** 249 commits, mostly plugins/embedders;
retrieval touched by `554bb98e`, `e8204062` (PolarDB inline vector
search), `1466ab08`. No ranking-formula change.

**Worth stealing / not.** *Steal* the PolarDB shape — `ts_rank` and
`<=>` in one table, tenant-filtered — and add the ORDER BY it omits.
*Not* an append-only JSON usage list nothing reads, nor per-tier rerank
then global sort across incomparable scores.

## 6. Code-search products (public writing)

**Sourcegraph / zoekt (a9206004).** Trigram-indexed substring/regex
engine with no index-time tokenization, separately indexing filenames
and ctags/tree-sitter symbol spans. Default `scoreFile`
(`index/score.go:302`) takes the **max line score** per file from
`index/contentprovider.go:591-609`: exact symbol-span match 7000 (edge
5500, overlap 4000), full-basename 7000, word match 500 (partial 50),
times a symbol-kind multiplier (class 10×, struct 9.5×, enum 9,
interface/type 8, function/method 7, field 5.5, const 5, variable 4;
`:720`) and an atom term `(1 − 1/n)·400` for multi-clause queries; then
`ScoreOffset·score + 100·repoRank + 10·docOrder` as tie-breaks
(`score.go:352`), where `repoRank` is months-since-1970 of the latest
commit or stars normalized at a 5,000-star midpoint (`api.go:678-700`)
and `docOrder` is index-time sorting (skipped/generated/vendored/test
last; short name, many symbols, small size first; `index/builder.go:891`).
Opt-in `UseBM25Scoring` (`scoreFileBM25`, `score.go:363`) sums
tf-saturated terms with k=1.2, b=0.75, **IDF held constant**,
filename/symbol hits counted 5× (`importantTermBoost`),
test/vendored/generated tf ÷5 — the BM25F the April 2025 blog describes
— and line-level BM25F (`score.go:206`, average line 100 bytes) picks
the display lines. Sourcegraph layers a PageRank-like SCIP
inbound-reference file rank on top (indexed-ranking doc). Aggregation is
per file with a "novel extension" boost into slot 3; content matches
suppress filename matches; each line gets N context lines. The blog's
semantic mode is BM25 first stage + transformer reranker.

**GitHub code search (Blackbird).** Rust engine over a sharded ngram
index — trigrams plus "sparse grams" that widen to rarer variable-length
grams where common trigrams are unselective — deduped by blob SHA
(115 TB → 28 TB) and sharded by blob SHA. Ranking is *baked into
document-id order*: "Compaction also k-merges the posting lists by score
so relevant documents have lower IDs and will be returned first by the
lazy iterators"; matches are validated, scored, shards aggregated,
re-sorted, permission-filtered, top 100 returned. The 2023 post names no
signals; the 2021 history post does: "ranking up definitions and
penalizing test code … ranking up complete matches and penalizing
partial matches, so that when searching for `thread` an identifier
called `thread` will rank above `thread_id`, which will rank above
`pthread_getname_np`," plus repository popularity. No user sorting; 100
cap; default branch only. Snippet method unstated beyond term
highlighting. 2025–26 work is on the Copilot side: instant semantic
indexing (Mar 2025) and a contrastive/Matryoshka embedding model with
hard negatives (+37.6% retrieval quality, 8× smaller index; Sep 2025).

**Cursor.** Remote chunk-embedding index synced by a Merkle tree of
per-file hashes rolled into directory hashes (only divergent branches
walked); chunks are "syntactic" (tree-sitter per third-party reporting),
embeddings cached by chunk content; a new user of a known repo
bootstraps from a simhash-matched index and must prove possession of
each file's hash before results are returned. Server storage holds
"embeddings without storing filenames or source code. Filenames are
obfuscated and code chunks are encrypted … decrypts the chunks on the
client side." Ranking: a custom embedding model trained on LLM-ranked
agent traces ("which content would have been most helpful at each
step"), no reranker described (Nov 2025 semsearch post). Explicitly
hybrid: "Our agent makes heavy use of grep as well as semantic search,
and the combination of these two leads to the best outcomes" (+12.5% QA
accuracy), with Instant Grep for named symbols. Results are chunks with
obfuscated path + line range; no file aggregation or file priors are
described.

**Augment Code (Context Engine).** Server-side embedding index built
with "custom context models that we specifically trained to identify the
most helpful context," prioritizing "helpfulness over relevance";
near-real-time indexing ("many thousands of files per second"),
per-developer per-branch indexes sharing shards within a tenant,
proof-of-possession gating. At 100M+ LOC: quantized ANN candidate
generation then full-precision embedding rescoring (8× memory, <200 ms,
99.9% parity) — two-stage but not a learned cross-encoder. Commit
history is summarized and "chunked and embedded alongside normal file
chunks" (Context Lineage, Jul 2025). Marketing: "not just grep or
keyword matching … retrieves the right slice before the model spends
tokens exploring." Nothing public states BM25/hybrid, file priors, or
snippet cutting.

**Claude Code.** No index. Anthropic's context-engineering post
describes "just in time" retrieval — "primitives like glob and grep
allow it to navigate its environment and retrieve files just-in-time,
effectively bypassing the issues of stale indexing and complex syntax
trees," conceding "runtime exploration is slower than retrieving
pre-computed data." Boris Cherny on Latent Space: early versions "used
RAG … just off-the-shelf RAG," but "we landed on just agentic search …
it outperformed everything. By a lot … mostly vibes"; and "the code
drifts out of sync … security issues because this index has to live
somewhere"; net "at the cost of latency and tokens, you now have really
awesome search without security downsides." Ranking is the model's
iteration (Glob → Grep → Read, Explore subagents); snippets are raw grep
lines; aggregation is whatever the model decides.

| Product | Index | Ranking signals | File aggregation | Snippet method |
|---|---|---|---|---|
| Sourcegraph/zoekt | trigram + filename + symbol spans | symbol 7000 / basename 7000 / word 500; kind boost 10×…4×; atom count; opt-in BM25F (k 1.2, b 0.75, constant IDF, filename+symbol tf ×5, test/vendored ÷5); repo rank; index-order prior; SCIP inbound-ref rank | max line score per file; novel extension into slot 3 | lines by heuristic or line-BM25F, N context lines; content hits suppress filename hits |
| GitHub Blackbird | sharded ngram + sparse grams, blob dedup | definitions up, tests down, complete > partial, repo popularity; baked into doc-id order | per-doc score, shard k-merge, top 100 | undisclosed; term highlighting |
| Cursor | remote chunk embeddings, Merkle-synced, encrypted | custom trace-trained embeddings; hybrid with Instant Grep; no reranker | none (chunk level) | syntactic chunk, decrypted client-side |
| Augment | server-side custom embeddings, real-time, per-branch | "helpfulness" embeddings; quantized ANN + full rescoring | not described | chunks |
| Claude Code | none | model iteration over glob/grep/read | model decides | raw grep lines |

## 7. Hybrid search in SQL (vendor docs)

**ParadeDB / pg_search** (AGPL; docs only). Recommends **RRF
exclusively** — "discards the scores and uses only each row's position,
or rank" — with no normalized-score alternative. Shape: two CTEs each
`RANK() OVER (ORDER BY ...) LIMIT 20`, fused by **`UNION ALL` + `GROUP
BY id` + `SUM(...)`**, not `FULL OUTER JOIN`: text leg `WHERE description
||| 'query'` ordered by `pdb.score(id) DESC, id` contributes
`1.0/(60 + rank)`; vector leg ordered by `embedding <=> '[...]'`
(pgvector HNSW) contributes `0.7/(60 + rank)` — **k = 60**, weights in the
numerators, ties broken by `id`. `pdb.score()` is **true BM25** from the
Tantivy-backed `USING bm25` index. No built-in hybrid function.

**VectorChord-bm25.** `bm25vector` column via `tokenize(text,
tokenizer)` (`pg_tokenizer`: BERT, unicode + NLTK stopwords), `CREATE
INDEX ... USING bm25`, queried as `embedding <&> to_bm25query(...)`
returning the **negated BM25** so `ORDER BY ... LIMIT` works. Vector leg
is `vchordrq` (RaBitQ). The hybrid guide runs both `LATERAL ... LIMIT
topk` queries separately and does **RRF in Python** with k = 60,
unweighted; a cross-encoder benchmark (FiQA nDCG@10: semantic 0.403,
BM25 0.253, RRF 0.376, cross-encoder 0.427) shows RRF loses slightly to
the reranker but is "much, much faster." No SQL fusion, no weights.

**Supabase `hybrid_search`.** A published SQL function:
`hybrid_search(query_text, query_embedding vector(512), match_count,
full_text_weight = 1, semantic_weight = 1, rrf_k = 50)`. CTE `full_text`
= `row_number() over (order by ts_rank_cd(fts, websearch_to_tsquery)
desc)` filtered by `@@`, `limit least(match_count, 30) * 2`; CTE
`semantic` = `row_number() over (order by embedding <#> q)`, same limit;
`FULL OUTER JOIN` on id; ordered by `coalesce(1.0/(rrf_k + ft.rank),
0)·w_ft + coalesce(1.0/(rrf_k + sem.rank), 0)·w_sem`. **k defaults to
50**, per-leg pool = 2× the final count capped at 60. Lexical is
`ts_rank_cd` — **not BM25**. Vector is pgvector `<#>` over HNSW.

**Azure SQL / SQL Server.** The Microsoft blog states "SQL Server and
Azure SQL don't offer a native RRF() function" and hand-builds it:
keyword leg `SELECT TOP(@k) ... FREETEXTTABLE(t, *, @q) ... ORDER BY
[RANK] DESC`; vector leg `TOP(@k) ... VECTOR_DISTANCE('cosine', @e,
col) ... ORDER BY distance`; `RANK() OVER` each; `FULL OUTER JOIN` with
`COALESCE(1.0/(@k + ss.rank), 0) + COALESCE(1.0/(@k + ks.rank), 0)`. In
the shipped sample **`@k = 10` is both the per-leg TOP and the RRF
constant** ("commonly 60 or equal to requested result count"). Lexical:
**`FREETEXTTABLE` ranking "is based on the OKAPI BM25 ranking formula"**
(k1 1.2, b 0.75, k3 8.0), whereas **`CONTAINSTABLE` is not BM25**
(`HitCount·16·Log2((2+IndexedRowCount)/KeyRowCount)/MaxOccurrence`,
capped 1000, relative only). Vector: `VECTOR` + `VECTOR_DISTANCE`
(exact) or SQL Server 2025 `VECTOR_SEARCH(TABLE=, COLUMN=, SIMILAR_TO=,
METRIC=)` over a DiskANN `CREATE VECTOR INDEX`, queried as `SELECT TOP
(N) WITH APPROXIMATE ... ORDER BY distance` (ASC only; window functions
and UNION need a subquery wrapper).

**Oracle 26ai hybrid vector index.** The one engine with a **built-in
primitive**. `CREATE HYBRID VECTOR INDEX idx ON t(col) PARAMETERS
('MODEL m [VECTOR_IDXTYPE HNSW|IVF]')` builds one Oracle Text domain
index whose `$I` table is the inverted index and whose `$VR` table holds
chunks + embeddings; it **must vectorize via an in-database ONNX model**
and cannot be pointed at an existing `VECTOR` column. Query is
`DBMS_HYBRID_VECTOR.SEARCH(json('{...}'))` returning JSON. Parameters:
`search_fusion` ∈ {`UNION` (default), `INTERSECT`, `TEXT_ONLY`,
`VECTOR_ONLY`, `MINUS_TEXT`, `MINUS_VECTOR`, `RERANK`}; `search_scorer` ∈
{**`RSF` (default)** = weighted sum of normalized scores, `RRF`, `WRRF`};
`vector.search_mode` `DOCUMENT` (aggregator `MAX` default, also AVG/SUM)
or `CHUNK`; per-leg `score_weight` (vector 10, text 1), `rank_penalty` =
the RRF k per leg (**vector 1, text 5** — not 60), `result_max`,
`return.topN` 20, and `score_calc` for a custom expression. **The brief's
`SEMANTIC_FIRST`/`KEYWORD_FIRST` mode names do not appear in the docs** —
the `search_fusion` values above are the equivalents. Vector distances
are rescaled to a 0–100 "semantic score" beside `CONTAINS` scores.
Oracle Text `SCORE` is Salton-style inverse frequency, **not BM25**.

**MariaDB 11.8.** KB page "Optimizing Hybrid Search Query with RRF":
**k = 60**, equal weights, per-leg `LIMIT 10`; vector leg `ORDER BY
VEC_DISTANCE_EUCLIDEAN(embedding, @vec) LIMIT 10` (the index-eligible
shape over `VECTOR INDEX ... DISTANCE=cosine|euclidean`, modified HNSW);
fulltext leg `MATCH(...) AGAINST(@q)` ordered desc `LIMIT 10`; each gets
`1/(@k + RANK() OVER (...))`. Because **MariaDB and MySQL have no `FULL
OUTER JOIN`**, fusion is `v LEFT JOIN f USING(id)` `UNION` `f LEFT JOIN v
USING(id)` with `IFNULL(partial_rrf, 0)` sums. InnoDB relevance is
**not BM25** (word counts and weights; MyISAM drops >50%-frequency
terms). No primitive.

**SingleStore.** Documents both a raw-score blend
(`w_t·COALESCE(MATCH ... AGAINST, 0) + w_v·COALESCE(DOT_PRODUCT, 0)`)
and **weighted RRF**, saying RRF "tends to be superior to ad-hoc ranking
methods like simply adding a full-text score to a vector dot product
score." RRF: CTEs `fts` and `vs` each top **200**, `ROW_NUMBER() OVER
(ORDER BY SCORE DESC)`, `FULL OUTER JOIN`, `0.7·(1/(NVL(fts_rank, 1000)
+ 60)) + 0.3·(1/(NVL(vs_rank, 1000) + 60))` — **k = 60, weights
0.7/0.3, a missing leg imputed rank 1000 rather than 0**. `FULLTEXT
USING VERSION 2` is Lucene-based and **"uses BM25 scoring"**; `BM25()` /
`BM25_GLOBAL()` use partition- and table-level statistics. Vector:
`VECTOR(n)` + `DOT_PRODUCT`/`<*>` with an ANN index.

**pgvector's own README and SQLite.** pgvector shows only the lexical
leg (`ts_rank_cd`) and points to `pgvector-python/examples/hybrid_search/rrf.py`
— the canonical shape everyone copies: two `RANK() OVER` CTEs at `LIMIT
20`, `FULL OUTER JOIN`, `COALESCE(1.0/(k + r), 0)` sums, **k = 60**,
unweighted. For SQLite, Alex Garcia's sqlite-vec post: `vec_matches`
(`row_number() over (order by distance)` from `vec0 ... match :q and k =
:k`), `fts_matches` (`row_number() over (order by rank)` — FTS5's hidden
`rank` is **true `bm25()`**, negative-is-better), `FULL OUTER JOIN`
(**requires SQLite ≥ 3.39**), `rrf_k = 60`, weights 1/1, k = 10; plus
keyword-first and rerank-by-semantics variants.

| Product | Fusion | k / weights / per-leg cap | Lexical fn — true BM25? | Vector leg | Built-in hybrid? |
|---|---|---|---|---|---|
| ParadeDB pg_search | RRF (UNION ALL + GROUP BY SUM) | 60; 1.0 text / 0.7 vec; 20 | `pdb.score()` — yes | pgvector `<=>` HNSW | no |
| VectorChord-bm25 | RRF in Python | 60; equal; topk | `<&>` negated BM25 — yes | vchordrq | no |
| Supabase | weighted RRF, FULL OUTER JOIN | **50**; 1/1; `2·n` ≤ 60 | `ts_rank_cd` — no | pgvector `<#>` HNSW | published SQL fn |
| Azure SQL / SQL Server | RRF, FULL OUTER JOIN | 10 in sample ("commonly 60"); equal | `FREETEXTTABLE` — yes (Okapi); `CONTAINSTABLE` — no | `VECTOR_DISTANCE` exact / `VECTOR_SEARCH` DiskANN | no |
| Oracle 26ai | **RSF default**, RRF, WRRF | rank_penalty vec 1 / text 5; score_weight 10/1; topN 20 | Oracle Text `SCORE` — no | in-index HNSW/IVF from ONNX | **yes** |
| MariaDB 11.8 | RRF via UNION of two LEFT JOINs | 60; equal; 10 | `MATCH AGAINST` — no | `VEC_DISTANCE_*` HNSW | no |
| SingleStore | weighted RRF (miss = rank 1000) or blend | 60; 0.7/0.3; 200 | Lucene v2 / `BM25()` — yes | `DOT_PRODUCT` ANN | no |
| pgvector README | RRF, FULL OUTER JOIN | 60; equal; 20 | `ts_rank_cd` — no | `<=>` | no |
| SQLite FTS5 + sqlite-vec | weighted RRF, FULL OUTER JOIN (≥3.39) | 60; 1/1; 10 | `bm25()` — yes | `vec0` MATCH k | no |

## Comparison

| System | Lexical leg | Vector leg | Fusion | Graph / centrality in ranking | Read/access signal in ranking | Cross-collection merge | Rerank |
|---|---|---|---|---|---|---|---|
| graphify 0.9.50 | label substring tiers + label-IDF, trigram prefilter | none (by design) | none — seeds then traversal; order by hop, degree | degree as hub penalty (p99) and tie-break; betweenness only in reports | recorded (`reflect`), **deliberately not fed back** | offline graph composition; single graph per query | none |
| gbrain 0.46.30 | `ts_rank`/`ts_rank_cd` (no IDF) | pgvector HNSW, `ef_search` sized | client-side weighted RRF (k = 60/weight), 0.7·RRF + 0.3·cos, boost tower | backlink log-boost, adjacency ×1.05 | `last_retrieved_at` written, not ranked | `source_id = ANY()` per arm; brains not federated | cross-encoder + identity tier + autocut |
| HippoRAG 2 | none | dense facts + passages (in-memory) | PPR over reset vector (passage prior 0.05) | PPR *is* the ranking; seed IDF | none | stores bulk-loaded; none | LLM fact filter |
| LightRAG | none | 3 vdbs, cosine ≥ 0.2 | round-robin interleave, no scores | degree/edge degree order relations for prompt | none | positional round-robin | optional external |
| graphrag 3.1 | none | per-field collections | token-budget proportions | degree/`combined_degree` stored as `rank` | none | in-memory joins | LLM ratings |
| cognee 1.5 | in-process BM25 mode only | multi-collection cosine, raw distance | identity overwrite; RRF k∈[30,60] in hybrid lane | PageRank in reports only | `last_accessed` written, not ranked; feedback EMA gated off | per-collection top-k, no normalization | truth-subspace |
| graphiti 0.29 | Lucene/RediSearch BM25 (rank only) | in-DB cosine ≥ 0.6 | RRF **k = 1**, 2·limit per leg | 1-hop distance bucket; mention count | none | four scopes, concatenated | cross-encoder, MMR |
| letta (archived) | Turbopuffer BM25 or `LIKE` | pgvector, unindexed | RRF k = 60, 0.5/0.5 | none | none | multi-archive raises | none |
| mem0 2.0 | `ts_rank_cd` / adapter keyword search | vector store | additive (sem + sigmoid-BM25 + entity)/max | entity-link boost | **platform only**: 0.3×–1.5× decay | none | optional |
| memori 3.3 | in-process BM25 | in-Python cosine over 1k pool | 0.85·cos + 0.15·bm25 | none | write-side `num_times` orders the pool | none | none |
| MemOS 2.0 | in-process BM25; PolarDB `ts_rank` | in-DB cosine | dict union, per-path rerank, global sort | key/tag graph match | `usage` written (writer now disabled), unread | per-cube buckets, extended | cosine or BGE |
| zoekt / Sourcegraph | trigram + symbol/basename tiers; opt-in BM25F | BM25 first stage + reranker (semantic mode) | single scorer, max line per file | SCIP inbound-ref file rank; repo rank | none | per-repo shards, score merge | transformer (semantic) |
| GitHub Blackbird | ngram + sparse grams | none (Copilot side separate) | score baked into doc-id order | repo popularity | none | shard k-merge | none |
| Cursor / Augment | grep (Cursor) / none stated | trace-trained embeddings | hybrid by agent (Cursor); ANN + rescoring (Augment) | none stated | none stated | per-branch shards | none / rescoring |
| Claude Code | grep | none | model iteration | none | none | none | none |

## Bearing on vfs

**Positioning statement.** Nothing in this field does what `glean` is
specified to do. Every graph-RAG system (graphify, HippoRAG, LightRAG,
graphrag, cognee) treats the graph as the retrieval model and either
has no lexical leg or bolts on an in-process BM25 over rows it already
pulled into memory; every agent-memory system (letta, mem0, memori,
MemOS) and gbrain fuses *outside* the database, usually with
hand-calibrated multiplicative boosts, and none of the open-source ones
rank on reads; the code-search products that do have principled ranking
(zoekt's BM25F with file priors, GitHub's baked-in doc order) are
purpose-built inverted indexes, not SQL; and the SQL vendors have
converged on one RRF recipe but ship it as copy-paste SQL, with true
BM25 available on only half the engines and a real hybrid primitive on
one (Oracle, with its own k defaults and no support for an existing
vector column). `glean`'s combination — the fusion statement executed by
the engine that owns the rows, glob scope and trash/permission
predicates inside each leg, portable across six dialects, with centrality
and read signals as declared inputs to a ranker API and an honest
envelope — is unoccupied. graphify in particular is not a competitor on
retrieval: it is a label matcher plus traversal whose own skill has to
rewrite the question into graph vocabulary because the engine cannot
match a synonym, and its authors have deferred the one ranking-feedback
idea they had for exactly the reason the brief's gap 5 names.

**Takeaways.**

1. **RRF by rank, `UNION ALL` + `GROUP BY`, k = 60, per-leg cap ≈ 2–5×
   limit, explicit tie-break.** The vendor record (§7) is unanimous that
   only rank is portable across incomparable lexical scorers, and the
   ParadeDB shape avoids `FULL OUTER JOIN`, which MariaDB/MySQL lack,
   SQLite gained only at 3.39, and SQL Server 2025's `VECTOR_SEARCH`
   forces into a subquery. Weighted RRF (Supabase, SingleStore, gbrain's
   k/weight) is the one knob the ranker API needs at launch; convex
   combination (Oracle's RSF default, mem0's additive sum) is what the
   harness (gap 8) should test against, not the default. Graphiti's
   k = 1 and Oracle's per-leg `rank_penalty` 1/5 show k is contested
   enough to be a declared parameter, not a constant.
2. **The lexical leg must carry document frequency, so it is ours, not
   the engine's.** `ts_rank`, `CONTAINSTABLE`, InnoDB relevance, and
   Oracle `SCORE` are not BM25 (§7); gbrain documents the resulting
   noise (§2); zoekt holds IDF constant but boosts filename/symbol
   *term frequencies* inside one saturating scorer rather than summing
   field scores (§6). The brief's portable `(term, chunk_id, tf)` table
   scored by a SUM is the shape that gets true BM25 on all six engines,
   and BM25F-style field boosts (path segment, symbol name) fold into it
   as tf multipliers.
3. **Per-entity aggregation in SQL before the user LIMIT, max-pool
   first.** gbrain's shared `DISTINCT ON (source, slug)` CTE (§2),
   Oracle's `DOCUMENT` mode with `MAX` aggregator (§7), zoekt's max line
   score per file (§6), and graphrag's `(entity_order, −count)` ordering
   all land on MaxP with a deterministic secondary key. Gap 2's answer is
   in the statement, not after it.
4. **Identity beats ranking; degrade honestly.** gbrain's exact-lookup
   tier and title arm, zoekt's basename 7000, GitHub's "complete match
   over partial" — a query naming a path must land at rank 1 without
   consulting the fusion. And every system that survived production grew
   an explicit fallback: HippoRAG's dense-only path, gbrain's
   `degraded[]` trail, graphify's top-of-output truncation notice,
   Cursor's grep alongside embeddings. Gap 1 (unembedded rows) and gap 9
   (tier served) are one envelope record family.
5. **Read signals: bounded multiplicative factor with a modification-time
   fallback, and nothing in the open-source record to copy.** mem0's
   platform decay (0.3×–1.5× over an over-fetched pool) is the only
   published design; memori's write-side `num_times` shows a free
   transactional counter; graphify's explicit deferral ("needs propensity
   correction + exploration") and cognee's `feedback_influence = 0.0`
   default are the field admitting the click-bias trap. Capture as an
   append-only event table rolled up at reindex (gap 5), enter the fusion
   as a bounded prior, and treat position-bias correction as a harness
   experiment, not a launch feature. Centrality has the same shape:
   HippoRAG's seed-IDF (`1/COUNT(chunk)`) and graphify's p99 hub rule
   both say degree is a *dampened* prior, never an additive score.

## Sources

Reference checkouts (read-only, `~/Git/Repos/<repo>`; commits as in the
header): graphify `graphify/serve.py`, `analyze.py`, `cluster.py`,
`reflect.py`, `ingest.py`, `global_graph.py`, `affected.py`,
`ARCHITECTURE.md`, `CHANGELOG.md`, `README.md`,
`docs/how-it-works.md`, `docs/node-summaries-rfc.md`,
`graphify/skills/kilo/references/query.md`, `graphify/always_on/claude-md.md`;
gbrain `src/core/search/{hybrid,sql-ranking,mode,intent-weights,autocut,
exact-lookup,graph-signals,recency-decay,relational-recall,dedup}.ts`,
`src/core/postgres-engine.ts`, `src/core/vector-index.ts`,
`src/core/last-retrieved.ts`, `docs/architecture/{RETRIEVAL,brains-and-sources}.md`,
`CHANGELOG.md`; HippoRAG `src/hipporag/{HippoRAG,rerank,embedding_store}.py`,
`utils/config_utils.py`; LightRAG `lightrag/{operate,base,utils,constants}.py`,
`kg/neo4j_impl.py`; graphrag `packages/graphrag/graphrag/query/structured_search/*`,
`context_builder/*`, `config/defaults.py`; cognee
`cognee/modules/retrieval/*`, `modules/search/*`,
`modules/graph/cognee_graph/*`, `infrastructure/databases/vector/*`,
`tasks/memify/apply_feedback_weights.py`; graphiti
`graphiti_core/search/{search,search_config,search_utils,search_filters}.py`,
`graph_queries.py`, `helpers.py`, `driver/*`; letta (at `87fd37aab^`)
`letta/orm/passage.py`, `services/agent_manager.py`,
`services/helpers/agent_manager_helper.py`, `helpers/tpuf_client.py`;
mem0 `mem0/memory/main.py`, `mem0/utils/scoring.py`,
`mem0/vector_stores/pgvector.py`, `docs/platform/features/memory-decay.mdx`,
`docs/changelog/highlights.mdx`; memori `memori/search/{_core,_lexical}.py`,
`memori/storage/drivers/sqlite/_driver.py`, `memori/storage/migrations/_sqlite.py`;
MemOS `src/memos/memories/textual/tree_text_memory/retrieve/{searcher,recall,
task_goal_parser}.py`, `src/memos/graph_dbs/{neo4j,polardb}.py`,
`src/memos/mem_scheduler/schemas/monitor_schemas.py`; zoekt
`index/{score,contentprovider,builder,eval}.go`, `api.go`.

Public pages:
- https://graphify.com/blog/introducing-graphify
- https://www.ycombinator.com/companies/graphify-labs
- https://www.augmentcode.com/learn/graphify-63k-stars-knowledge-graphs
- https://sourcegraph.com/blog/keeping-it-boring-and-relevant-with-bm25f
- https://sourcegraph.com/blog/new-search-ranking
- https://raw.githubusercontent.com/sourcegraph/sourcegraph-public-snapshot/main/doc/dev/background-information/architecture/indexed-ranking.md
- https://github.blog/engineering/architecture-optimization/the-technology-behind-githubs-new-code-search/
- https://github.blog/engineering/architecture-optimization/a-brief-history-of-code-search-at-github/
- https://docs.github.com/en/search-github/github-code-search/about-github-code-search
- https://github.blog/changelog/2025-03-12-instant-semantic-code-search-indexing-now-generally-available-for-github-copilot/
- https://github.blog/news-insights/product-news/copilot-new-embedding-model-vs-code/
- https://cursor.com/blog/secure-codebase-indexing
- https://cursor.com/docs/context/codebase-indexing
- https://cursor.com/blog/semsearch
- https://www.augmentcode.com/blog/a-real-time-index-for-your-codebase-secure-personal-scalable
- https://www.augmentcode.com/blog/repo-scale-100M-line-codebase-quantized-vector-search
- https://www.augmentcode.com/blog/announcing-context-lineage
- https://www.augmentcode.com/context-engine
- https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents
- https://www.latent.space/p/claude-code
- https://code.claude.com/docs/en/best-practices
- https://www.paradedb.com/docs/documentation/hybrid/rrf.md
- https://www.paradedb.com/docs/documentation/hybrid/overview.md
- https://www.paradedb.com/docs/documentation/sorting/score.md
- https://www.paradedb.com/blog/hybrid-search-in-postgresql-the-missing-manual
- https://www.paradedb.com/learn/search-concepts/reciprocal-rank-fusion
- https://github.com/tensorchord/VectorChord-bm25
- https://docs.vectorchord.ai/vectorchord/use-case/hybrid-search.html
- https://blog.vectorchord.ai/hybrid-search-with-postgres-native-bm25-and-vectorchord
- https://supabase.com/docs/guides/ai/hybrid-search
- https://devblogs.microsoft.com/azure-sql/enhancing-search-capabilities-in-sql-server-and-azure-sql-with-hybrid-search-and-rrf-re-ranking/
- https://github.com/Azure-Samples/azure-sql-db-openai/blob/main/vector-embeddings/07-hybrid-search.sql
- https://learn.microsoft.com/en-us/sql/relational-databases/search/limit-search-results-with-rank
- https://learn.microsoft.com/en-us/sql/t-sql/functions/vector-search-transact-sql?view=sql-server-ver17
- https://docs.oracle.com/en/database/oracle/oracle-database/26/arpls/dbms_hybrid_vector1.html
- https://docs.oracle.com/en/database/oracle/oracle-database/26/vecse/understand-hybrid-search.html
- https://docs.oracle.com/en/database/oracle/oracle-database/26/vecse/understand-hybrid-vector-indexes.html
- https://docs.oracle.com/en/database/oracle/oracle-database/26/vecse/create-hybrid-vector-index.html
- https://docs.oracle.com/en/database/oracle/oracle-database/26/ccref/oracle-text-scoring-algorithm.html
- https://mariadb.com/docs/server/reference/sql-structure/vectors/optimizing-hybrid-search-query-with-reciprocal-rank-fusion-rrf
- https://mariadb.com/docs/server/reference/sql-structure/vectors/vector-overview
- https://mariadb.com/docs/server/ha-and-performance/optimization-and-tuning/optimization-and-indexes/full-text-indexes/full-text-index-overview
- https://docs.singlestore.com/cloud/developer-resources/functional-extensions/hybrid-search-re-ranking-and-blending-searches/
- https://www.singlestore.com/blog/hybrid-search-using-reciprocal-rank-fusion-in-sql/
- https://docs.singlestore.com/cloud/reference/sql-reference/full-text-search-functions/bm-25/
- https://github.com/pgvector/pgvector
- https://github.com/pgvector/pgvector-python/blob/master/examples/hybrid_search/rrf.py
- https://alexgarcia.xyz/blog/2024/sqlite-vec-hybrid-search/index.html
- https://simonwillison.net/2024/Oct/4/hybrid-full-text-search-and-vector-search-with-sqlite/
