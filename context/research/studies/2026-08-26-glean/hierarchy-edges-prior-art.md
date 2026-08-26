# Hierarchy edges in an importance prior: how the field treats containment next to references

- **Study for**: `context/research/2026-08-26-glean-ranking-signals-and-ranker-api.md`
  §2 (centrality as a static prior — in particular §2.3's "no
  directory-adjacency fallback graph" rule) and
  `context/decisions/018-edge-authoring-verbs-and-materialized-fs-edges.md`
  (the filesystem hierarchy is materialised into `edges` as reserved
  `edge_type='fs'` rows, directory → child). Clay wants those fs edges to
  join glean's static centrality prior at a lower weight than reference
  edges; this study asks what the field does. Glean ranking only — graph
  traversal verbs are out of scope.
- **Date**: 2026-08-26
- **Sources** (reference checkouts under `~/Git/Repos`, read-only, cited
  and described — no code copied):
  - graphify `v8` @ `43d54ac` — `graphify/ingest.py`, `graphify/analyze.py`,
    `graphify/cluster.py`, `graphify/extract/*`, `graphify/mcp_server.py`,
    `graphify/rerank.py`, `docs/how-it-works.md`, `ARCHITECTURE.md`.
  - gbrain @ `872c3d6` — `src/core/search/graph-signals.ts`,
    `src/core/search/graph-signals-shared.ts`,
    `src/core/search/graph-signals-compat.ts`, `src/core/search/hybrid.ts`,
    `src/core/search/interfaces.ts`, `src/core/db/migrations/*.ts`,
    `src/core/links/*.ts`, `docs/concepts/*.md`.
  - graphrag @ `f40e9a2` — `packages/graphrag/graphrag/index/operations/*`,
    `index/workflows/*`, `data_model/schemas.py`,
    `query/context_builder/*`, `query/structured_search/*`.
  - LightRAG @ `812f2d5d` — `lightrag/operate.py`, `lightrag/base.py`,
    `lightrag/kg/networkx_impl.py`, `lightrag/kg/neo4j_impl.py`.
  - cognee @ `690c0ec02` — `cognee/modules/graph/*`, `cognee/tasks/graph/*`,
    `cognee/infrastructure/databases/graph/*`, `cognee/modules/retrieval/*`,
    `cognee/modules/engine/models/*`, `cognee/modules/data/processing/*`.
  - HippoRAG @ `2f52a86` — `src/hipporag/HippoRAG.py`,
    `src/hipporag/embedding_store.py`, `src/hipporag/utils/config_utils.py`.
  - jackrabbit-oak `trunk` @ `a3d05a4` — `oak-doc/src/site/markdown/query/*`,
    `oak-search/src/main/java/org/apache/jackrabbit/oak/plugins/index/search/*`,
    `oak-lucene/src/main/java/org/apache/jackrabbit/oak/plugins/index/lucene/*`,
    `oak-core/.../plugins/index/reference/*`.
  - zoekt @ `a9206004` — `index/builder.go`, `index/score.go`,
    `index/eval.go`, `index/contentprovider.go`, `index/filecategory.go`,
    `index/indexdata.go`, `api.go`, and the history commits `f6d0aa00`
    (#523) and `c7f1e697` (#853).
  - scip @ `a7b9c65` — `scip.proto`.
  - networkx @ `cfc6b79` — `networkx/algorithms/link_analysis/pagerank_alg.py`,
    `networkx/algorithms/centrality/katz.py`, `networkx/classes/function.py`.
  - rustworkx @ `e02dc7ce` — `rustworkx/rustworkx.pyi`,
    `src/link_analysis.rs`, `src/centrality.rs`.
  - kuzu @ `89f0263` — `extension/algo/src/main/algo_extension.cpp`,
    `extension/algo/src/function/page_rank.cpp`,
    `extension/algo/test/test_files/{page_rank,wcc,spanning_forest}.test`,
    `dataset/ldbc-sf01/schema.cypher`, `test/test_files/recursive_join/*`.
    ladybug @ `109d0b2` — `src/extension/extension_entries.cpp`,
    `test/answers/show_functions.csv`, `test/test_files/function/gds/*`
    (its `extension/` submodule is not checked out).
  - neo4j @ `eccd584a` (branch `2026.06`) is the kernel source only — no GDS
    or docs; the Graph Data Science material below comes from the public
    docs (URLs in *Web sources* at the end).
  - Web: Neo4j GDS PageRank / ArticleRank / graph projection docs;
    Sourcegraph "Ranking in a week" (Eric Fritz's mirror — the
    sourcegraph.com copies return 403 to this tool); GitHub's Blackbird
    posts; Elasticsearch `path_hierarchy` tokenizer; Vespa `uri` fields;
    SharePoint ranking-model docs (UrlDepth, ClickDistance); Eiron,
    McCurley & Tomlin, *Ranking the Web Frontier* (WWW 2004, HostRank /
    DirRank); Xue et al., *Exploiting the Hierarchical Structure for Link
    Analysis* (SIGIR 2005, Hierarchical Rank); aider's repo map; deprank.
- **Executed**: nothing — this is a reading study. The measurements it
  leans on are the companion study's
  (`centrality-and-read-signals.md` §A: 440-file markdown link graph,
  synthetic scaling runs).

## Question

vfs stores the directory tree twice: `entries.parent_id` (the write-side
arbiter) and a materialised `edges` row per live non-root entry —
`edge_type='fs'`, source = parent directory, target = child — in the
same table that will carry caller-authored and, later, extracted reference
edges (imports, markdown links, symbol uses). glean's static prior is
"centrality over live `edges`", in-degree by default with PageRank/Katz as
declared alternatives. The owner wants the fs rows to *participate* in
that prior at a lower weight than reference rows rather than be filtered
out.

Two things the field can tell us: (1) when a system computes an
importance score for search ranking over a graph that *also* has a
containment/hierarchy relation, how does it hold the two apart — as
edge-type filters, as a weight on the edge, as an aggregation level, as
a separate scalar feature, or not at all; and (2) has anyone actually
folded a directory tree into a PageRank-style prior, and what happened.

The template per system: **Hierarchy modelled as** · **Enters
ranking?** · **How weighted** · **Worth noting**.

---

## 1. Graph-RAG and agent-memory systems

### 1.1 graphify (v8 @ `43d54ac`)

- **Hierarchy modelled as**: not modelled. The ingester walks the tree
  (`graphify/ingest.py:1-38` — a file-discovery and classification step,
  respecting `.gitignore` and skipping `node_modules`/`.git`/`__pycache__`)
  and never mints a directory node or a `contains`/`part_of` edge; every
  extractor's output is a node with a `source_file` *attribute*
  (`graphify/extract/python.py:120-131` and `:157-169` — nodes carry
  `source_file`, `source_location` and a `line` span; there is no
  file-level node). The relation vocabulary is `calls`, `imports`,
  `inherits`, `decorates`, `references`, `attribute_access`,
  `type_annotation`, plus the semantic `defines`, `uses`, `explains`,
  `depends_on`, `contradicts` (`graphify/extract/python.py:87-98`,
  `:106-107`, `:152-154`; `ARCHITECTURE.md:32-38`). `defines` there is
  "concept defined by a passage", not "file defines symbol". The
  directory shows up in exactly one place — the **community label**
  (`graphify/cluster.py:56-63` picks the longest common source-path prefix
  among a cluster's nodes as its name).
- **Enters ranking?**: no hierarchy relation exists to enter it. The
  "god nodes" are plain `G.degree()` sorted descending over every edge
  in the graph (`graphify/analyze.py:20-33`); hub detection that penalises
  traversal is a p99-degree cutoff (`graphify/mcp_server.py:158-160`;
  `docs/how-it-works.md:150-169` says hubs above p99 are "skipped when
  ranking"). Edge `confidence` (EXTRACTED 1.0 / INFERRED 0.6 / AMBIGUOUS
  0.3 — `ARCHITECTURE.md:99-104`, `docs/how-it-works.md:71-80`) exists on
  every edge but is *not* an input to degree or clustering, which are
  unweighted (`graphify/cluster.py:23-30` runs Leiden on all edges,
  unweighted; the file's own docstring says the `weight` param is
  unused).
- **How weighted**: n/a for hierarchy. No PageRank, Katz or betweenness
  anywhere (`grep -rn pagerank|centrality|betweenness` finds only the
  degree-based hub logic). Ranking is retrieval-side reranking with
  degree read *once* to bias budget (`graphify/rerank.py:117-125`).
- **Worth noting**: graphify is the clearest case of "the tree is
  metadata on the node, not an edge". Its one use of hierarchy — naming
  a cluster by a shared path prefix — is a *labelling* use of the tree,
  a projection from graph to directory, the opposite direction from
  folding the tree into the graph.

### 1.2 gbrain (`872c3d6`)

- **Hierarchy modelled as**: a *page-type taxonomy* plus a page →
  content-section containment, neither of which is an edge in the link
  graph. The `page_type` column (`entity`, `concept`, `source`,
  `dataset`, `people`, `projects`, … — `src/core/db/migrations/006_*.ts`)
  is the closest thing to a hierarchy; content is split into `content`
  rows keyed by `page_id` (`src/core/db/migrations/003_*.ts`). Slugs are
  path-like (`sources/foo`, `people/bar`) but the slug prefix is never
  a relation. The `links` table (`src/core/db/migrations/008_*.ts`:
  `source_page_id`, `target_page_id`, `link_type`, `link_text`,
  `is_resolved`) is minted from wikilinks and markdown links by
  `src/core/links/link-extractor.ts` — no `parent`/`contains`/`child`
  link type exists.
- **Enters ranking?**: link signals do; hierarchy does not. The graph
  signal is a per-page **backlink count**: `SELECT target_page_id,
  COUNT(*) FROM links GROUP BY …` over the candidate set
  (`src/core/search/graph-signals.ts:48-70`), and a second
  **connection-count / link-density** feature over both directions
  (`graph-signals-shared.ts:12-40`). The hybrid pipeline adds them to the
  fused RRF score as a bounded bonus: `min(backlinks, cap) × weight`
  with `cap` and `weight` constants in `src/core/search/hybrid.ts:20-31`
  — a clamp rather than a log, which the companion study rates as the
  crude end of the transform family. Path/folder never enters a score;
  `grep -rn "folder|directory|depth"` in `src/core/search` hits only
  slug-prefix *filters* (`interfaces.ts` page-type and slug-prefix
  filter options).
- **How weighted**: one edge kind, one weight; there is no per-link-type
  weight table.
- **Worth noting**: gbrain keeps the taxonomy as a *filter axis*
  (page_type, slug prefix) and the links as the *score axis* — exactly
  the split the companion memo's §2.3 recommends. Its `last_retrieved_at`
  column is written and never ranked (already recorded in
  `centrality-and-read-signals.md` §5).

### 1.3 graphrag (`f40e9a2`)

- **Hierarchy modelled as**: two hierarchies, both held *out* of the
  graph the degree is computed on. (a) Containment: document → text
  unit → entity/relationship is stored as id-list columns —
  `text_unit_ids` on entities and relationships, `document_ids` on text
  units, `entity_ids`/`relationship_ids` on text units
  (`data_model/schemas.py:20-98`); the input loaders keep the source
  path as a `title`/metadata attribute (`index/input/util.py`). (b) The
  community tree: hierarchical Leiden (`index/operations/cluster_graph.py`)
  writes `level`, `parent`, `children` columns on the `communities`
  table (`index/workflows/create_communities.py`, `schemas.py:101-130`),
  never a `parent_of` edge.
- **Enters ranking?**: only the entity-relationship graph. `degree` is
  computed by `compute_degree` over the graph whose edges are the
  extracted relationships (`index/operations/compute_degree.py`), and a
  relationship's `combined_degree` is `source.degree + target.degree`
  (`index/operations/compute_edge_combined_degree.py`). That number is
  stamped as `rank` on relationships and used at query time to order
  in-network and out-network relationships in local search context
  (`query/context_builder/local_context.py` — sort by `rank`, then
  weight). Community `rank` is different — it is the LLM-assigned
  "importance rating" of the community report
  (`index/operations/summarize_communities/*`, the `rating`/`rank`
  field), and global search uses it as a `community_rank`-threshold /
  sort (`query/structured_search/global_search/community_context.py`).
- **How weighted**: relationships carry a `weight` (extraction count /
  LLM strength summed across text units in `index/operations/extract_graph/*`),
  but `degree` is unweighted node degree; containment carries nothing
  because it is not an edge.
- **Worth noting**: graphrag has the richest hierarchy in the set
  (document → unit → entity, plus a community tree) and keeps *all* of
  it as columns. The community tree is used for *level selection* and
  *context assembly* (which reports to show), never as a prior on
  entities. `prune_graph.py` drops low-degree nodes and low-weight
  edges by threshold — the tree could not be there without inflating
  every entity's degree by one.

### 1.4 LightRAG (`812f2d5d`)

- **Hierarchy modelled as**: `source_id` and `file_path` fields on every
  node and edge (`lightrag/operate.py` — the entity/relation merge
  stamps a `GRAPH_FIELD_SEP`-joined list of chunk ids and file paths;
  `lightrag/base.py` documents the fields). Chunks and documents are
  KV/vector rows, never graph nodes.
- **Enters ranking?**: `rank` = `node_degree(entity)` and, for edges,
  `edge_degree = degree(src) + degree(tgt)`
  (`lightrag/kg/networkx_impl.py` `node_degree`/`edge_degree`;
  `lightrag/kg/neo4j_impl.py` the same by `count(r)`), computed on the
  entity graph only and used to sort entities/relations in the prompt
  context (`operate.py` — sort by `rank` then `weight`). Since chunk
  containment is a field, it never contributes a degree.
- **How weighted**: edge `weight` (LLM strength, summed on merge) is a
  secondary sort key, not a degree input.
- **Worth noting**: LightRAG's `source_id` carries a *multiplicity*
  (how many chunks mention this entity) that is a containment-derived
  count kept as a field — the same idea as an in-degree from
  chunk→entity edges, but stored without minting the edges.

### 1.5 cognee (`690c0ec02`)

- **Hierarchy modelled as**: real edges. Every `DataPoint` relation is
  materialised in the graph store — `DocumentChunk -[is_part_of]->
  Document`, `Entity -[is_a]-> EntityType`, `DocumentChunk -[contains]->
  Entity`, `Summary -[made_from]-> Chunk` (`cognee/modules/engine/models/*`,
  `cognee/modules/graph/utils/get_graph_from_model.py` — the model's
  typed fields with `metadata["index_fields"]`/relationship annotations
  become `(source_id, target_id, relationship_name, properties)` tuples;
  `cognee/tasks/storage/add_data_points.py` writes them as ordinary
  edges). Datasets are tables in the relational store, not nodes; file
  paths are node properties.
- **Enters ranking?**: not for retrieval. The graph-completion and
  triplet retrievers score by vector distance over node/edge embeddings
  (`cognee/modules/retrieval/graph_completion_retriever.py`,
  `utils/brute_force_triplet_search.py`); nothing in that path reads a
  degree. PageRank/degree appear only in the *report* retriever
  (`cognee/modules/retrieval/graph_report_retriever.py` — networkx
  `pagerank` with a degree fallback when scipy is absent), which
  summarises the graph, and there they run on the *whole* graph, so
  `is_part_of`/`contains` edges do count — a Document node's degree is
  its chunk count, an Entity's degree includes every chunk that
  mentions it.
- **How weighted**: unweighted; the report retriever passes no `weight`
  and there is no per-relationship-name multiplier. `feedback_influence`
  is `0.0` by default (the retrieval-side popularity knob, unrelated to
  structure).
- **Worth noting**: cognee is the one graph-RAG system with containment
  as first-class edges, and the consequence is visible in its own
  report — degree there measures *chunk multiplicity* more than
  reference structure. It is a description of the corpus, not a prior
  that ranks search results, so nothing was tuned around it.

### 1.6 HippoRAG (`2f52a86`)

- **Hierarchy modelled as**: a bipartite containment edge family
  *inside* the PPR graph. The graph has phrase nodes and passage nodes;
  edge families are (a) fact edges phrase ↔ phrase from extracted
  triples, weighted by triple count; (b) synonymy edges phrase ↔ phrase
  above an embedding-similarity threshold; (c) **passage ↔ phrase
  "context" edges** — every passage is connected to every phrase
  extracted from it (`src/hipporag/HippoRAG.py`, `add_fact_edges`,
  `add_passage_edges`, `augment_graph`/`add_synonymy_edges`;
  `embedding_store.py` for the passage/entity stores).
- **Enters ranking?**: yes — and it is load-bearing, not a low-weight
  extra. `run_ppr` runs igraph personalised PageRank (damping 0.5,
  `graph_search_with_fact_entities`) seeded on the phrases of the
  query's matched facts; the *passages* are what gets ranked, and the
  only route from a phrase's score to a passage is the containment edge.
  Passages also receive a small direct seed (`passage_node_weight`,
  default 0.05, `utils/config_utils.py`) so the DPR leg contributes.
- **How weighted**: containment edges are weight 1 like the fact edges
  (fact edges carry the triple count); the asymmetry is applied to the
  *seed*, not the edge — a phrase's personalisation weight is divided by
  the number of passages it appears in (the hub-dampening already noted
  in `centrality-and-read-signals.md` §2.1).
- **Worth noting**: this is the single system in the set where
  containment edges sit in a PageRank and it works — because the score
  is *query-time and personalised* and the containment edge is the
  bridge to the ranked entity type, not a prior. HippoRAG never computes
  a global PageRank of this graph; if it did, passage rank would be
  phrase count.

## 2. Hierarchy-native content and code search

### 2.1 jackrabbit-oak (`a3d05a4`)

- **Hierarchy modelled as**: address space, indexed for *filtering*. Every
  indexed node carries two structural fields — `:ancestors`
  (`FieldNames.java:45`), a `TextField` stored `NO`
  (`oak-lucene/.../FieldFactory.java:158`) analysed with
  `PathHierarchyTokenizerFactory` (`LuceneIndexDefinition.java:148`, one
  token per path prefix), and `:depth` (`FieldNames.java:50`), an
  `IntField` (`FieldFactory.java:162`). `ISDESCENDANTNODE` becomes
  `TermQuery(:ancestors, path)` (`LucenePropertyIndex.java:1077`);
  `ISCHILDNODE` adds a `NumericRangeQuery` pinning `:depth` to exactly
  parent-depth + 1 (`:1082-1084`, `:1598-1600`). All of it is gated by
  `evaluatePathRestrictions` (`IndexDefinition.java:282,468,685-686`;
  `oak-doc/.../query/lucene.md:194-196,620-682`). The Elastic index
  always writes both fields (`ElasticDocument.java:173-174`) and
  `elastic.md:36-37` says the switch "cannot be disabled".
- **Enters ranking?**: no. Elastic puts every non-fulltext constraint,
  path included, into `bool.filter` (`ElasticRequestHandler.java:249-251`;
  the recorded fixture `ElasticIndexQueryCommonTest.java:83-111` shows
  the `:ancestors` term inside the filter clause) — score-free by design. Lucene
  keeps them as `MUST` clauses of the scored query, but every hit of a
  given query shares the same ancestor term and depth value, so the
  contribution is a constant that shifts `jcr:score` without reordering.
  `jcr:score` is Lucene's `ScoreDoc.score` passed straight through
  (`LucenePropertyIndex.java:330`) from a vendored, unmodified Lucene
  4.7.2 similarity — no Oak subclass exists.
- **How weighted**: every boost knob is per *property*, never per tree
  position: `PropertyDefinition.boost` (`PropertyDefinition.java:58,79,178`),
  query-time `term^N` (`LucenePropertyIndex.java:1493-1494`), `dynamicBoost`
  (`lucene.md:1241-1271`) which reads `confidence` values off *child*
  tag nodes to boost the parent — a schema-specific child→parent flow,
  de-weighted by a fixed `DYNAMIC_BOOST_WEIGHT` (`:1561-1563`). Aggregation
  (`Aggregate.java:269-341`; `lucene.md:709-813`) copies descendant text
  into the ancestor's `:fulltext` so a parent *matches* on a child's
  words; there is no `boost` field anywhere in `Aggregate.java` and no
  depth-dependent multiplier. The reference index
  (`oak-core/.../reference/ReferenceIndex.java:55,78-141`) is a
  constant-cost equality lookup — reference *count* is never a score.
- **Worth noting**: the one hierarchy-native store in the set has no
  notion of a node's importance at all. What it *does* do with the tree
  is the model for the non-score uses: a path-prefix term for scoping,
  an integer depth for child-vs-descendant, and content aggregation
  (child text folded into the parent) — a containment relation used to
  make the parent *findable*, not to make it *rank*.

### 2.2 zoekt (`a9206004`)

- **Hierarchy modelled as**: two path-*content* features, never depth.
  (a) `FileCategory` (`index/file_category.go:31-63`) — go-enry's
  `IsTest`/`IsVendor`/`IsGenerated`/`IsDotFile`/`IsConfiguration`/
  `IsDocumentation` matching directory-name fragments anywhere in the
  path (`vendor/`, `node_modules/`, `test/`) — binary, position-blind: a
  ten-deep `vendor/` is the same as a root one. (b) A basename-vs-rest
  split in `scoreLine` (`index/score.go:127-148`): a filename match that
  spans the whole basename gets `scoreBase` 7000, one touching a basename
  edge 5500, one inside the basename `scorePartialBase` 4000, and one
  confined to a parent directory segment **nothing** beyond the generic
  word-match points (constants at `index/contentprovider.go:589-610`).
- **Enters ranking?**: category does, twice — as features 2–4 of the
  nine-element index-time sort vector `rank()`
  (`index/builder.go:891-942`: skipped, generated, vendored, test,
  `squashRange(len(Name))`, symbol count, content length, branch count,
  original index; `squashRange(x)=x/(1+x)` at `:876-880`), which becomes
  the query-time tiebreaker `docOrderScore × scoreFileOrderFactor(10)`
  (`index/score.go:339-352`); and as BM25's `lowPriorityFilePenalty = 5`
  term-frequency divisor (`:253-254,272-276`). Path *length* — feature 5,
  raw byte length of the full relative path, not a segment count — is
  the only path-shape feature, and it is a tiebreaker below category.
  Repository `Rank` (`api.go:632,678-702`; `gitindex/index.go:334-353`
  — stars/forks traction squashed as `1 − 1/(1+log t)^0.6`, or a recency
  fallback) is one scalar per repo at weight 100.
- **How weighted**: no per-file structural weight exists any more. The
  external per-path "document rank" (#460, Sourcegraph's SCIP rank file)
  was fused by RRF, then by weighted sum and removed from index ordering
  (#523, `f6d0aa00`), then deleted with all plumbing (#853, `c7f1e697`).
  Nothing replaced it.
- **Worth noting**: a repo-wide grep finds no `/`-counting, no "is in
  root", no depth scaling in `builder.go`, `score.go`, `eval.go`,
  `contentprovider.go`, `matchtree.go` or `indexdata.go`. Where zoekt
  uses the tree it asks *what the path says* (test? vendored? does the
  query hit the basename?) not *where the file sits*. The basename bonus
  is the closest thing to a hierarchy-aware score and it is a
  query-dependent match feature, not a prior.

### 2.3 SCIP (`a7b9c65`) and Sourcegraph's file rank

- **Hierarchy modelled as**: SCIP has *no* containment relationship
  between documents and symbols, packages and symbols, or directories
  and documents. `Relationship` has four booleans — `is_reference`,
  `is_implementation`, `is_type_definition`, `is_definition`
  (`scip.proto`, message `Relationship`); `SymbolRole` is a bitmask of
  `Definition`, `Import`, `WriteAccess`, `ReadAccess`, `Generated`,
  `Test`, `ForwardDefinition` (message `SymbolRole`). Containment is
  encoded two other ways, neither an edge: `SymbolInformation.
  enclosing_symbol` (a string, "the symbol that encloses this one",
  meant for local symbols) and the **symbol string's own grammar** —
  `scheme ' ' manager ' ' package ' ' version ' ' descriptors`, where
  descriptors nest as package `/`, type `#`, term `.`, method `(…).`,
  parameter `(…)`, meta `:`, macro `!` — so a symbol's ancestors are
  recoverable by parsing its name. A directory is never an entity; a
  `Document` has a `relative_path` string.
- **Enters ranking?**: Sourcegraph's file rank ("inbound references from
  any other file in the available code graph … inspired by PageRank",
  *Ranking in a week*) was built from occurrences only: files are nodes,
  "an edge between two documents indicates a reference of a symbol
  (variable, function, type, etc) defined in another file"; the
  hierarchy is "not discussed". They tried directed edges both ways and
  settled on **undirected** — "directional edges tended to rank
  auto-generated files with tons of definitions (e.g., a protobuf code
  gen) very highly, but rank `main`-like files that refer to lots of
  definitions but define few themselves very low … undirected edges …
  boost files with multiple distinct edges". Ranks were packed into
  zoekt's index order and its `9000 × min(1, log₂count/32)` document
  rank (companion study), then removed in zoekt #853.
- **How weighted**: unweighted, undirected file graph; aggregation to
  the repository was by summing/ordering.
- **Worth noting**: the largest code-search practitioner's graph had
  neither a directory node nor a file→symbol edge; its one structural
  fix was *dropping direction*, because definition-heavy generated
  files were the failure mode. A fs edge would have pointed the same
  way as the failure (into the container).

### 2.4 GitHub code search (Blackbird)

- **Hierarchy modelled as**: paths are a filter (`path:`) and a
  tokenised field; "The technology behind GitHub's new code search"
  describes ranking only as "k-merges the posting lists by score so
  relevant documents have lower IDs" — a static index order like
  zoekt's.
- **Enters ranking?**: the published heuristics are "ranking up
  definitions and penalizing test code", "ranking up complete matches
  and penalizing partial matches", and repository popularity (stars) —
  no directory-depth or folder signal is described.
- **Worth noting**: the two signals that *are* path-derived (test-code
  penalty, definition boost) are categorical features computed from the
  path string, the zoekt `fileCategory` pattern, not graph edges.

## 3. Web and enterprise search: the tree as a feature, a grouping, or a teleport set

### 3.1 SharePoint / FAST ranking model

- **Hierarchy modelled as**: two static scalar rank features. **UrlDepth**
  — "the number of backslashes in the URL of a document", transformed
  by `InvRational` (k = 1.5 in the worked example) so "documents with
  shorter URLs receive higher rank scores"; and **ClickDistance** — the
  number of clicks from an authoritative page (Meyerzon & Zaragoza's
  Microsoft patents), transformed `InvRational` (k ≈ 0.276 in the
  default model) with layer-1 weight ≈ 0.62. The default 2013 model's
  nine features are BM25F, FileType, language, ClickDistance, UrlDepth,
  QLogClicks, QLogSkips, QLogLastClicks, EventRate, combined linearly
  (first stage) or by a one-hidden-layer network (second stage).
- **Enters ranking?**: yes, as *the* structural prior in an intranet
  where "link popularity based measures can be limited".
- **How weighted**: a transformed scalar with its own weight, additive
  with BM25F — never an edge in a link computation.
- **Worth noting**: this is the production precedent for "the tree
  matters": depth is a feature of the *entry*, click distance is a
  distance-from-root on a hierarchy that includes navigation links, and
  both are saturating transforms of a small integer — exactly the
  "path-shape signal, a column expression, not a graph" that the
  companion memo's §2.3 names.

### 3.2 Eiron, McCurley & Tomlin — HostRank and DirRank (WWW 2004)

- **Hierarchy modelled as**: an *aggregation level*. HostRank collapses
  every page on a host into one node with host→host edges weighted by
  link count and row-normalised; **DirRank** collapses URLs "that agree
  up to the last '/'" into one node ("virtual directory"), 1.08 B pages
  → 114 M directory nodes, edges between directories. Section 7.1 also
  records the original PageRank paper's suggestion of teleporting "to a
  randomly selected top-level page of a site" and measures why: 62.4 %
  of links are site-internal and external links go to the top level
  (82 % once dynamic URLs are excluded).
- **Enters ranking?**: yes, as a *replacement* for page PageRank —
  cheaper (an order of magnitude fewer nodes) and "more resistant to
  direct manipulation", with the per-page rank inherited from the
  directory/host.
- **How weighted**: no parent→child edge is ever added; the tree
  changes *what the nodes are*, not what the edges are.
- **Worth noting**: the paper's own observation that external links
  concentrate on roots is the empirical reason depth works as a prior —
  and the reason a parent→child edge in PageRank is redundant with it.

### 3.3 Xue, Yang, Zeng, Yu & Chen — Hierarchical Rank (SIGIR 2005)

- **Hierarchy modelled as**: aggregation again, with a second step:
  "Web pages are first aggregated based on their hierarchical structure
  at directory, host or domain level and link analysis is performed on
  the aggregated graph … The importance of each node on the aggregated
  graph is distributed to individual pages belong to the node based on
  the hierarchical structure" — a rank *dissipation down the tree*.
- **Enters ranking?**: yes; on TREC .GOV 2003/2004 it "consistently
  outperforms … PageRank, BlockRank and LayerRank", and "link
  aggregation at the host level is much better than … the domain or
  directory levels".
- **Worth noting**: this is the closest thing in the literature to
  "fold the tree into PageRank", and it does it as *aggregate → rank →
  distribute*, motivated by sparsity and new-page bias — the two
  problems a vfs mount has (53 % zero in-degree on this repo's link
  graph; new entries have no in-links). Notably the *directory* level
  did worst of the three.

### 3.4 Elasticsearch `path_hierarchy` and Vespa `uri`

- **Hierarchy modelled as**: tokens. `path_hierarchy` emits a term per
  prefix (`/one`, `/one/two`, `/one/two/three`), with `reverse`, `skip`
  and `delimiter` options; the documented "common use-case … is
  filtering results by file paths". Vespa's `uri` field type splits a
  URL into `scheme`, `hostname`, `port`, `path`, `query`, `fragment`
  components addressable as `field.path:term`.
- **Enters ranking?**: only as term matches — a query term that matches
  a path token scores like any other term; neither engine derives a
  depth or ancestry *feature*. The idiom for a depth prior in both is an
  application-computed numeric field (`rank_feature` / `attribute(depth)`)
  in a `function_score` or rank-profile expression.
- **Worth noting**: the two most-deployed search engines treat the path
  as *addressable structure for filtering and faceting* and leave any
  hierarchy-derived score to a scalar the application computes.

### 3.5 Agent-side PageRank over code: aider's repo map and deprank

- **Hierarchy modelled as**: not at all. aider's repo map is a directed
  file graph — an edge from the referencing file to the defining file
  per identifier — with multiplicative edge weights (×10 for identifiers
  named in the chat, ×10 for "real-looking" names, ×50 for edges out of
  files already in the chat) and a personalisation vector over chat
  files, run through `networkx.pagerank`; "no mention of directories,
  folders, or path depth". deprank runs PageRank over a
  dependency-cruiser import graph, files as nodes, "those files which
  are directly or indirectly depended upon the most".
- **Worth noting**: aider is the strongest evidence that per-edge
  multipliers by *edge kind* and a personalisation vector are the
  practical levers on a mixed graph — but every kind there is still a
  reference; hierarchy is delivered to the model as the tree rendering
  around the ranked symbols, not as rank.

## 4. Libraries: what a mixed-weight prior needs from the kernel

### 4.1 networkx (`cfc6b79`)

`pagerank(G, alpha=0.85, personalization=None, max_iter=100, tol=1e-6,
nstart=None, weight="weight", dangling=None)`
(`networkx/algorithms/link_analysis/pagerank_alg.py`): `weight` names an
edge attribute; `None` makes every edge 1; on a MultiGraph parallel
edges are summed. `personalization` is a dict node → weight, normalised
to sum 1 (missing nodes get 0); `dangling` is the distribution dangling
mass is sent to (defaults to `personalization`). The implementation is
the scipy sparse power iteration (`_pagerank_scipy`) — networkx ≥ 3
raises without scipy. `katz_centrality(G, alpha=0.1, beta=1.0, …,
weight=None)` accepts the same per-edge attribute and a per-node `beta`
dict (`networkx/algorithms/centrality/katz.py`). `G.in_degree(weight=…)`
gives the weighted in-degree that the zeroth iteration is. Per-edge-
*type* weights are not an API concept: the caller stamps a numeric
attribute per edge from the type before the call.

### 4.2 rustworkx (`e02dc7ce`)

`pagerank(graph, alpha=0.85, weight_fn=None, nstart=None,
personalization=None, tol=1e-6, max_iter=100, dangling=None)`
(`rustworkx/rustworkx.pyi`, `src/link_analysis.rs`): `weight_fn` is a
Python callable on the edge payload — the natural place for a
`{"fs": 0.2, "ref": 1.0}` lookup; `personalization` and `dangling` are
dicts by node index; `katz_centrality(graph, alpha, beta, weight_fn,
default_weight, max_iter, tol)` likewise (`src/centrality.rs`). `hits`
exists. PyDiGraph only; no pure-Python fallback (companion study §2.4).

### 4.3 Neo4j GDS (docs)

`relationshipWeightProperty`: "the previous score of a node sent to its
neighbors is multiplied by the relationship weight and then divided by
the sum of the weights of its outgoing relationships"; negative weights
are ignored; unset means unweighted. `sourceNodes` accepts node ids or
`[[nodeId, bias], …]` pairs for personalised PageRank. Graph projection
accepts a *list of relationship types* or a map with **per-type
property defaults** (`properties: {w: {property: 'w', defaultValue:
…}}`), `aggregation` (`NONE|SINGLE|COUNT|MIN|MAX|SUM`) for parallel
relationships, and `orientation` (`NATURAL|UNDIRECTED|REVERSE`) — so a
projection of `[FS, REF]` with `defaultValue` 0.2 on `FS` and 1.0 on
`REF` is the idiomatic way to express "hierarchy at a lower weight".
**ArticleRank** is the hub-tempering variant: it "lowers the influence
of low-degree nodes" by adding the average out-degree to the
denominator — relevant because a directory with two children is
exactly a low-out-degree source that plain PageRank over-credits. The
docs offer no guidance on hierarchies or trees.

### 4.4 kuzu (`89f0263`) / ladybug (`109d0b2`)

`PROJECT_GRAPH(name, nodeTables, relTables)` takes several rel tables
with per-table filter predicates (`extension/algo/test/test_files/
page_rank.test:91-105` projects `['knows','studyAt']` and runs
`page_rank` on it), so an `fs` + `ref` union graph is one projection —
but `page_rank` is **unweighted** (`extension/algo/src/function/
page_rank.cpp:25-68` accepts only `dampingFactor`, `maxIterations`,
`tolerance`, `normalizeInitial`; `:138-166` divides by plain
out-degree). Weights exist only for `SPANNING_FOREST`
(`weight_property`) and Louvain, and for the recursive-join
`WSHORTEST(cost)` family. Hierarchy in the shipped LDBC schema is an
ordinary `Place-[:isPartOf]->Place` rel table
(`dataset/ldbc-sf01/schema.cypher:26`); multi-label recursion is
`[e:knows|:studyAt*1..2]` (`test/test_files/recursive_join/
multi_label.test:18`). ladybug's `extension/` is an uninitialised
submodule; `src/extension/extension_entries.cpp:28-30` and
`test/answers/show_functions.csv` (`PAGE_RANK(ANY,BOOL)`) indicate the
same unweighted algorithm. Neither has modelling guidance on trees.

---

## 5. Comparison

| System | Hierarchy modelled as | In the ranking graph? | Weight vs references | Score it feeds |
|---|---|---|---|---|
| graphify v8 | `source_file` attribute; cluster label from path prefix | no | — | degree ("god nodes"), p99 hub penalty |
| gbrain | page-type column, slug prefix, `content.page_id` | no (filter only) | — | backlink count, clamped, additive |
| graphrag | id-list columns; community `level/parent/children` columns | no | — | degree, `combined_degree`; LLM community rating |
| LightRAG | `source_id`/`file_path` fields | no | — | node degree, edge degree |
| cognee | real edges (`is_part_of`, `contains`, `is_a`, `made_from`) | yes, in the *report* PageRank only | 1.0 (unweighted) | not used for retrieval ranking |
| HippoRAG | passage ↔ phrase edges in the PPR graph | yes — the bridge to ranked passages | 1.0; hub dampening on the *seed* | query-time PPR, damping 0.5 |
| jackrabbit-oak | `:ancestors` path-prefix terms, `:depth` int; child text aggregated into parent | no (filter context; constant under Lucene) | — | stock Lucene/ES BM25 + per-property boost |
| zoekt | `FileCategory` from path fragments; basename-vs-rest match split; path byte length | as index-order tiebreaker and BM25 penalty | category binary; basename 7000/5500/4000/0 | match score ≫ repo rank ≫ doc order |
| SCIP / Sourcegraph | `enclosing_symbol` string, descriptor grammar, `relative_path` | no | — | undirected file-reference PageRank (since removed) |
| GitHub Blackbird | `path:` filter; test/definition categories from path | no | — | categorical boosts + repo stars |
| SharePoint | `UrlDepth`, `ClickDistance` scalar features | no graph | `InvRational` transform, own weight | linear / NN over features with BM25F |
| Eiron et al. 2004 | aggregation level (host, directory); root teleport | replaces the page graph | host→host edges weighted by link count | HostRank / DirRank |
| Xue et al. 2005 | aggregate → rank → distribute down the tree | replaces, then dissipates | — | Hierarchical Rank; host level best, directory worst |
| Elasticsearch / Vespa | path-prefix tokens; `uri` components | as term matches only | — | BM25 on tokens; app-computed depth field |
| aider / deprank | none (file graph) | no | per-kind ×10/×50 multipliers, personalisation | networkx PageRank |
| networkx / rustworkx / GDS | per-edge numeric weight, per-type default (GDS) | as configured | caller-stamped | PageRank, Katz, ArticleRank |
| kuzu / ladybug | ordinary rel table; multi-table projection | as configured | unweighted PageRank | PageRank |

---

## 6. Bearing on vfs

### 6.1 What the field does with containment in an importance score

Three postures, and the population is lopsided:

1. **Hold the tree out of the graph** — as an attribute, an id-list
   column, a filter term, or a categorical feature computed from the
   path string. graphify, gbrain, graphrag, LightRAG, SCIP/Sourcegraph,
   GitHub, Oak, zoekt, Elasticsearch and Vespa all do this. Where the
   tree *does* touch ranking in this group it is as a query-dependent
   match feature (zoekt's basename bonus) or a categorical prior
   (test/vendored/generated), never as an edge in a centrality.
2. **Put it in the graph as an ordinary edge, unweighted** — only where
   the resulting score is *not a search prior*: cognee (a PageRank
   report, where a document's degree becomes its chunk count) and
   HippoRAG (query-time personalised PageRank, where the passage↔phrase
   edge is the bridge that lets phrase evidence reach the passages
   being ranked). Neither computes a global rank of that graph and
   neither weights the containment family below the reference family;
   HippoRAG's only asymmetry is on the seed.
3. **Use the tree as a different kind of object**, which is where the
   published wins are:
   - a **scalar feature of the entry** — SharePoint's `UrlDepth` and
     `ClickDistance`, both `InvRational`-transformed with their own
     weight; Kraaij's URL-type and Craswell's "URL length" that still
     helped after PageRank (companion memo §2.1);
   - an **aggregation level** — Eiron's HostRank/DirRank and Xue's
     Hierarchical Rank collapse pages into their directory/host, rank
     the collapsed graph, and distribute the rank back down; motivated
     by sparsity and new-page bias, and Xue found the *directory* level
     the weakest of the three;
   - a **teleport set / personalisation vector** — the original
     PageRank suggestion of jumping to a site's top-level page, which
     Eiron grounds in the data (external links go to roots), and
     aider's chat-file personalisation on a pure reference graph.

### 6.2 Verdict: does anyone fold the tree into a PageRank-style prior?

No system in the set adds parent→child edges to a global PageRank,
Katz or in-degree that is then used as a static search prior, at any
weight. The nearest cases and what happened:

- **cognee** has the edges and runs PageRank over them, unweighted, for
  a *report*: degree there reads as container size (a Document's degree
  is its chunk count), which is why it is not wired into retrieval.
- **Sourcegraph** had no hierarchy edges but hit the same shape from
  the reference side: directed edges into definition-heavy containers
  (generated files) over-ranked them, so they switched to an
  *undirected* file graph — the fix was to change the graph, not to
  weight it — and the whole rank was later deleted from zoekt.
- **Xue 2005** is the one published "hierarchy inside link analysis"
  with measured gains, and it does not add edges: it aggregates,
  ranks, and dissipates down the tree; aggregating at the immediate
  directory did worst.
- **SharePoint** — the one production ranker with a hierarchy prior —
  made it a standalone saturating feature, not an edge.

### 6.3 What an `fs` edge does inside vfs's own measures

This is worth stating because "at a lower weight" reads differently
under each measure the companion memo declares:

- **In-degree, dir→child** (the default signal): every live non-root
  entry has exactly one fs in-edge (ADR 018 pin 6), so a weight `w` adds
  the constant `w` to every entry and vanishes under min-max
  normalisation. Harmless and worthless at any `w`.
- **In-degree, reversed or undirected**: a directory's in-degree becomes
  `w × child count` — a directory-size prior, the thing zoekt's
  vendored/generated categories exist to demote. Directories have no
  chunks and are not glean hits, so this rank is only ever a conduit —
  but under PageRank it is a conduit that flows.
- **PageRank / Katz, dir→child**: a directory receives almost only
  teleport mass (references target files, not directories) and pushes
  it to its children in proportion to `w / Σ out-weights`; a child in a
  small directory gets more than one in a large directory, and the
  effect compounds down the tree — Eiron's observation that a
  hierarchical link structure makes rank "decay exponentially as we
  descended the hierarchy". So the fs family at weight `w` is a
  **depth-and-sibling-count prior computed by power iteration**, which
  is what the memo's §2.3 already named and rejected as "a depth prior
  computed expensively". ArticleRank's tempering of low-out-degree
  sources would blunt the small-directory term, not remove it.

In none of these is the fs family a "lower-weight reference"; it is a
different signal wearing the centrality's name.

### 6.4 Patterns worth adopting

- **Keep the reference graph pure and make the type weight explicit.**
  The extract for `centrality` should carry a per-`edge_type` weight
  map (the aider / GDS `defaultValue` / rustworkx `weight_fn` idiom),
  compiled as a `CASE edge_type WHEN … END` multiplier or a type filter,
  with `fs` defaulting to `0` — and `0` meaning *excluded from the
  extract*, not "present at zero", so the default statement is the
  memo's `edge_type <> 'fs'`. A deployment that wants the tree in the
  graph opts in with a number; the option is visible in the
  `options_hash` and reversible.
- **Deliver "the tree at a lower weight" as a path-shape signal.**
  SharePoint's `UrlDepth` with `InvRational` and the Craswell/Kraaij
  URL-form results are the precedent: a declared `depth` signal —
  segment count from `entries` (a column expression, no graph, no
  extract phase), saturating transform `1/(1 + k·depth)`, small weight,
  present for every entry so the absent-signal rule never triggers.
  This is the cheapest thing in the study with a measured win.
- **If sparsity is the real motivation, borrow Hierarchical Rank's
  dissipation, not its edges.** 53 % of this repo's link graph has zero
  in-degree and new entries always do; Xue's cure was *aggregate →
  rank → distribute*. In vfs terms: a second declared measure,
  `smoothed in-degree` = `indeg(e) + λ · mean(indeg over siblings)` (or
  over the parent's subtree), computed as one join through the fs
  edges' single hop — SQL-expressible, incremental, and it gives an
  unlinked file in a well-linked directory a floor above zero. Xue's
  finding that coarse aggregation beat the immediate directory argues
  for `λ` small and the group possibly wider than siblings.
- **If the tree should bias PageRank, put it in the personalisation
  vector.** Every kernel in reach takes it (`personalization` in
  networkx, rustworkx, `sourceNodes` with bias in GDS; the memo's numpy
  loop adds one vector): teleport mass ∝ `1/(1+depth)` or concentrated
  on top-level entries reproduces the "jump to a site's front page"
  model without touching the edge set, and it composes with the
  hub-dampening HippoRAG applies on the seed side.
- **Use the tree for what the hierarchy-native systems use it for.**
  Oak and Elasticsearch: path-prefix terms for scoping (glob already
  does this in vfs), an integer depth for child-vs-descendant, and
  *content aggregation* — folding a child's text into the parent so a
  directory-level entry (a README, an index page) is findable on its
  children's terms. That is a chunking/previews question, not a
  ranking one, but it is the containment relation's proven job.

### 6.5 Net

The field's answer to "hierarchy edges next to reference edges in an
importance score" is: don't put them in the same sum. Keep the graph
signal a reference signal (typed weight map, `fs` excluded by default);
express the tree as its own transformed scalar (`depth`), as a
smoothing of the reference signal along the tree (Hierarchical Rank's
dissipation), or as PageRank's restart distribution — each of which
has a precedent that measured a gain, where folding containment into
the edge set has only precedents that were confined to reports, to
query-time PPR, or were abandoned.

---

## Web sources

- Neo4j GDS — PageRank: <https://neo4j.com/docs/graph-data-science/current/algorithms/page-rank/>;
  ArticleRank: <https://neo4j.com/docs/graph-data-science/current/algorithms/article-rank/>;
  graph projection: <https://neo4j.com/docs/graph-data-science/current/management-ops/graph-creation/graph-project/>
- Sourcegraph, "Ranking in a week" (Eric Fritz mirror):
  <https://www.eric-fritz.com/articles/ranking-in-a-week>; the
  sourcegraph.com blog and the `indexed-ranking` architecture doc
  returned 403 to this tool — the file-rank description quoted in the
  companion memo comes from the search-result snippet of
  <https://sourcegraph.com/blog/new-search-ranking>.
- GitHub, "The technology behind GitHub's new code search":
  <https://github.blog/engineering/architecture-optimization/the-technology-behind-githubs-new-code-search/>;
  "Improving GitHub code search":
  <https://github.blog/engineering/architecture-optimization/improving-github-code-search/>
- Elasticsearch `path_hierarchy` tokenizer:
  <https://www.elastic.co/guide/en/elasticsearch/reference/current/analysis-pathhierarchy-tokenizer.html>
- Vespa schema reference (`uri` field type):
  <https://docs.vespa.ai/en/reference/schemas/schemas.html>
- Microsoft Learn, "Customizing ranking models to improve relevance in
  SharePoint" (UrlDepth, ClickDistance, InvRational transform):
  <https://learn.microsoft.com/en-us/sharepoint/dev/general-development/customizing-ranking-models-to-improve-relevance-in-sharepoint>
- Eiron, McCurley, Tomlin, "Ranking the Web Frontier", WWW 2004
  (§7 HostRank, §8 DirRank): <https://www.mccurley.org/papers/1p309.pdf>
- Xue, Yang, Zeng, Yu, Chen, "Exploiting the Hierarchical Structure for
  Link Analysis", SIGIR 2005:
  <https://www.microsoft.com/en-us/research/publication/exploiting-the-hierarchical-structure-for-link-analysis/>
- aider repo map write-up: <https://anishgandhi.com/aider-pagerank-codebase-ranking/>;
  deprank: <https://github.com/codemix/deprank>
