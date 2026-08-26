# glean: fused ranked search across the database dialects (brief)

- **Status**: problem brief — the requirements audit that seeded the
  research leg. **Superseded 2026-08-26** by five memos, one per
  decision: [glean in the engine](2026-08-26-glean-in-the-engine.md),
  [fusion and cross-mount merge](2026-08-26-glean-fusion-and-cross-mount-merge.md),
  [ranking signals and the ranker API](2026-08-26-glean-ranking-signals-and-ranker-api.md),
  [the embedding seam](2026-08-26-glean-embedding-seam.md),
  [previews and the result shape](2026-08-26-glean-previews-and-result-shape.md);
  the landscape record and the no-requirements design stand as studies
  under `studies/2026-08-26-glean/`. Commits us to nothing.
- **Date**: 2026-08-26
- **Owner**: Clay Gendron
- **Question**: `glean` is pinned as one fused verb (ADR 007) and no
  backend implements it. What must the database backend's `glean` be —
  across Postgres, MariaDB, MySQL, SQL Server, Oracle, and SQLite — so
  that reciprocal rank fusion of vector similarity and BM25-style lexical
  search runs *inside* the engine, glob scoping pushes down with it,
  graph centrality and read-derived signals can join the fusion, results
  arrive as top-*n* entries with fast query-biased previews, and top-*n*
  lists from mounts with different embedders and lexical engines merge
  honestly?

---

## Why this exists

ADR 007 (`../decisions/007-fused-glean-search-surface.md`) fixed the
surface in July: `glean(query, *, limit=10, paths=(), ...)`, no strategy
selector, fusion behind the backend seam, "reciprocal rank fusion in the
reference design", centrality as index-time data feeding glean's graph
signal. The July multimodal memo
(`2026-07-25-multimodal-storage-and-search.md` §2.6, §4; studies
`studies/2026-07-25-multimodal-storage/vector-portability.md` and
`search-practice.md`) settled the vector *floor*: portable column,
scope-prefilter first, exact scan at the floor, server-side exact KNN
where a distance function exists, native ANN where indexes exist, and
declared per-dialect caps. It also recommended multi-space fan-out with
rank fusion for media. Neither document designed the lexical leg, the
fusion statement, the cross-mount merge, the embedding seam, the
preview, or the ranking-signal API. This brief scopes that research.

The active-spec closure pass is done (2026-08-25) and the reindex
pipeline now mints semantic chunk rows with an `embedding` column that
nothing fills — the seam glean rides on is built and idle.

## What exists today (ground truth for the memo)

- **Verb and router.** `VFS.glean` at `src/vfs/base.py:1252` gates
  params, fans out across mounts via `_route_fanout(row_cap=limit)`,
  and `_cap_rows` (`base.py:2635`) trims the merged list with
  `Result.top(k)` — a sort by `Observation.score`, which the docstring
  concedes is "only loosely comparable" across mounts. Params:
  `src/vfs/params.py:231` (`query`, `limit`, scope paths XOR
  observations, columns, user). Projection: `("path", "score")`
  (`src/vfs/results/projection.py:48`).
- **Backend protocol.** `SupportsGlean`
  (`src/vfs/storage/protocol.py:286`) — its own capability family; no
  live backend implements it.
- **Match model.** `Match(start, end, match, content, score)`
  (`src/vfs/models/entry.py:334`): grep/glean surface *regions*;
  `Observation.score` is the max across regions. This is the preview's
  carrier — a region with 1-indexed line bounds and its own text.
- **Chunks.** `chunks` table (`src/vfs/models/rows.py:424`): `(entry_id,
  chunk_index)`, `line_start`/`line_end`, `content_hash`, `encoded`,
  `embedding` (`VectorType`; pgvector-native when `NativeEmbeddingConfig`
  is set — `src/vfs/models/vector.py:49`), `content`. Chunk rows are
  minted on the reindex path by `Chunk.split_batch` (tree-sitter /
  notebook / recursive splitters; `src/vfs/models/chunk.py`), never on
  write (`2026-08-25-semantic-chunking-write-vs-reindex.md`). Embedding
  staleness is `embedding IS NULL`.
- **Reindex.** `DatabaseStorage.reindex`
  (`src/vfs/storage/backends/database/backend.py:461`) →
  `indexing.py`: assess dirty → split chunks (offloaded) → build gram
  postings under a fresh epoch → publish (flag flips + CAS pointer) →
  reclaim. One reindex at a time (lease). This is where embedding,
  centrality, and any derived ranking signal would be computed.
- **Grep's scope pushdown.** `grep.py` joins a segment-bounded glob scope
  as an allow-list before the candidate budget
  (`_entries_for_docs`, `_pushdown_terms`, `pathterms.py`,
  `segments.py`; ADR 040). Glean's glob filter has the same shape to
  reuse.
- **Gram index.** Entry-grain trigram postings for grep — exact-match
  only, no term frequencies, no positions. There is no lexical
  *ranking* index of any kind.
- **Dialects.** `DialectProfile` (`dialects.py`) declares only what
  SQLAlchemy does not model; `chunked`/`byte_chunked`/`membership_budget`
  bound every statement. Unknown engines resolve to `GENERIC`.
- **Graph.** `edges` table of ID triples with `edge_type` and `weight`
  (`rows.py:443`); edges are user-minted — nothing extracts them.
- **Read metrics.** None. No column, counter, or event table records that
  an entry was read.
- **Rendering.** `results/render.py` renders a `Result` to markdown
  (path list, table, block); there is no CLI module in `src/vfs` today —
  "CLI output" means the render layer's shape.
- **Fan-out budget.** Spec 051 (active) gives fan-out a deadline budget;
  glean's embed call and per-mount search must live under it.

## Clay's requirements (2026-08-26), as read

- **R1 — Fusion in the engine.** RRF of vector similarity and BM25-like
  lexical ranking, pushed down to the database as one statement per
  mount. The design must let index-time centrality (PageRank, Katz, or
  others computed in the reindex pipeline) and read-derived signals
  ("clicks") join the fusion — through a customizable ranker API.
- **R2 — Glob scoping.** `glean` takes a glob pattern like `grep` and
  filters results by it, pushed down as far as possible.
- **R3 — Cross-mount merge.** Each mount may run a different embedding
  model and a different lexical implementation. Clay's lean: an
  in-process BM25 reranker over the union of each mount's top-*n*,
  picking the corpus top-*n*. To be tested against prior art and the
  academic record, not assumed.
- **R4 — Embedding provider in Storage.** The provider embeds the query
  (the router hands the query string to storage, which embeds it) and
  the chunks. LangChain and OpenAI embedders supported out of the box;
  single and batch embedding for performance.
- **R5 — Entries, not chunks.** Top-*n* entries; output shows the path,
  the relevant line numbers, and a Google-style preview of the relevant
  chunks with keywords bolded. Preview selection must be fast.
- **R6 — Study set.** Fresh web perspective; graphify included (awareness,
  not imitation); one subagent researches with no requirements given.
- **R7 — Process.** Refresh every reference clone before study (now a
  CLAUDE.md rule).

## Gaps the memo must also settle (added by the audit)

1. **Freshness posture.** A content write leaves chunk rows with
   `embedding IS NULL` until reindex runs. grep's index tier unions a
   scan tier so staleness never loses a match; the vector leg has no
   scan analogue. What does glean return for an unembedded entry — the
   lexical leg alone, with a warning-severity record naming the count?
   The lexical leg needs the same decision (does it read a lexical
   index or the live text?).
2. **Per-entry aggregation.** Fusion ranks chunks; the verb returns
   entries. MaxP / SumP / FirstP and their fused variants have a
   literature (passage-level retrieval aggregation) — pick with evidence,
   and decide whether aggregation happens in SQL or after.
3. **Embedding identity and migration.** Native vector columns are
   fixed-dimension; the query must be embedded by the model that
   embedded the stored chunks. Model swap = re-embed the mount. The
   July memo's space registry (model → dimension → kinds) is the
   candidate shape; the memo should say where the model identity lives
   (mount config, `meta` row, column type) and how a mismatch refuses.
4. **Embedding at 10k-batch scale.** A 10,000-file reindex is ~10⁵
   chunks: request batching (input-count and token caps per request),
   concurrency, rate-limit backoff, cost, truncation of chunks longer
   than the model's context, and an embedding cache keyed on
   `(model, content_hash)` so unchanged chunks never re-embed. This is
   network I/O inside the reindex lease — heartbeat and lease TTL
   interact with it.
5. **Read metrics as writes.** Counting reads turns every read into a
   write: hot-row contention under agent concurrency, and a `read`
   inside a read-only transaction. Candidates: an append-only event
   table batched by the caller, periodic roll-up into a per-entry
   counter at reindex, decay. Which verbs count (read, not stat/ls),
   whether it is opt-in, and what a "click" means when the reader is an
   agent that reads everything it is shown. Position bias (clicks
   follow rank) is the known trap — the ULTR literature is the record.
6. **Centrality needs a graph.** Edges are user-minted only; no
   extractor exists. Centrality over the `edges` table is real for
   corpora that declare links (wikis, note graphs) and empty for a bare
   code tree. The memo should say what graph centrality reads (declared
   edges; directory adjacency; extracted references as a later
   producer) and how a zero-edge mount degrades (signal absent, not
   zero-weighted noise).
7. **Fusion arithmetic.** RRF is rank-only and parameter-sensitive
   (k); convex combination of normalized scores beats RRF in the 2023
   TOIS analysis but needs a tuned weight. Static priors (centrality,
   reads) fold in either as an extra ranked list or as a multiplicative
   boost — different semantics. Decide with an evaluation harness, not
   taste.
8. **Evaluation harness.** A ranking change without a relevance set is
   unmeasurable. The memo should propose a small golden corpus and
   query set (nDCG/MRR via ranx) that the ranker API's knobs are tuned
   against and that the conformance suite can pin for determinism
   (stable tie-breaks across engines).
9. **Result honesty.** Which tier served (native ANN / exact KNN /
   floor scan), approximate-recall contracts (Oracle's `TARGET
   ACCURACY`), unembedded counts, truncation — all as warning-severity
   records in the envelope, in the spirit of grep's truncation record.
10. **Trash, permissions, versions.** Trashed rows (`deleted_at`) are
    excluded exactly as grep excludes them; `user_id` scoping applies;
    version rows are never searched.
11. **Query shape.** Plain text, no operator language (operators would
    be a strategy selector by another name); an empty or whitespace
    query classifies `invalid`; a length cap tied to the embedder's
    context.
12. **Preview without keywords.** A vector-only hit has no query terms
    to bold; the preview then shows the top chunk's head with line
    bounds. Bolding is over folded/stemmed matches of the query's
    lexical terms against the chunk text already in hand — no second
    fetch.
13. **A rerank seam.** Clay's cross-mount BM25 reranker, a cross-encoder,
    or an LLM reranker are all "rerank the merged top-*n*" stages. The
    API should have one such seam even if only the BM25 one ships.
14. **Glean over `observations`.** Piping a prior result restricts the
    candidate set to those entries — the scope allow-list again, keyed
    by entry id instead of glob.

## What the memo needs to settle

### Engine and statement

1. **Per-dialect capability matrix, 2026.** For each of Postgres
   (+pgvector), MariaDB 11.8, MySQL 9 community, SQL Server 2025, Oracle
   23ai/26ai, SQLite (+FTS5, sqlite-vec): vector type and distance
   function availability, ANN index DDL, native full-text ranking
   function and whether it is BM25, and whether one SQL statement can
   express both legs plus RRF. Verified against the Docker legs, not
   docs alone.
2. **Lexical index: engine FTS or our own tables?** Engine FTS differs
   per dialect (ts_rank is not BM25; InnoDB FULLTEXT; CONTAINSTABLE;
   Oracle Text SCORE; FTS5 bm25()). A portable alternative is a
   term-frequency table `(term, chunk_id, tf)` plus document lengths,
   scored by a SUM in plain SQL on every engine — the gram index's
   sibling. Price both at linux-store scale.
3. **The fused statement.** The SQL shape per dialect: two ranked CTEs
   (or the engine's hybrid primitive — Oracle `DBMS_HYBRID_VECTOR`,
   MariaDB's documented RRF query), RRF in SQL, glob scope joined as an
   allow-list *inside* each leg, per-entry aggregation, `LIMIT n`.
   Bind-parameter and IN-list budgets apply.
4. **The vector floor in the fused statement.** On MySQL community and
   `GENERIC` there is no server-side distance: the vector leg is a
   client-side exact scan over the scoped set. The fusion then happens
   where? (Client-side RRF is the honest floor; the statement carries
   the lexical leg only.)

### Ranking

5. **Fusion function and its parameters**, with evidence: RRF (k),
   convex combination with min-max/z-score, weighted RRF; how static
   priors (centrality, reads, recency) enter.
6. **Passage-to-entry aggregation** (MaxP/SumP/…) and where it runs.
7. **Centrality in the reindex pipeline**: which algorithms (PageRank,
   Katz, HITS, degree) on which graph, computed how (networkx vs
   rustworkx vs SQL-iterative), stored where (entries column? a
   `signals` table keyed by `(entry_id, signal)`), refreshed when.
8. **Read-derived signals**: capture, roll-up, decay, and the click-bias
   record.
9. **The customizable ranker API**: what a backend exposes (registered
   signals with weights? a fusion function protocol? a rerank stage?)
   without breaking ADR 007's "no strategy selector on the verb".

### Cross-mount

10. **Merging top-*n* lists from heterogeneous mounts.** The federated
    search record (CORI, ReDDE, SSL, sample-based score estimation),
    the fusion-library record (ranx, OpenSearch normalization,
    haystack/llama_index joiners, LanceDB rerankers), and an executed
    simulation: one corpus split across mounts with different embedders,
    merge strategies scored against the single-index oracle. Verdict on
    Clay's in-process BM25 reranker.

### Provider

11. **The embedding seam in Storage.** Provider protocol (single + batch,
    async), LangChain and OpenAI adapters, an offline deterministic
    provider for tests (model2vec / fastembed / a hash embedder),
    batching limits, retries, cache, cost accounting, and how the router
    hands the query to storage.

### Output

12. **Preview generation.** Query-biased snippet selection over the
    chunks already fetched (Turpin 2007; Lucene's unified highlighter;
    tantivy's snippet generator; zoekt's line selection), keyword
    bolding, line-number reporting, and the `Match`/`Observation` shape
    plus `render.py` changes to carry it.

### Landscape

13. **graphify (v8, 0.9.50) and the field**: what graphify does for
    search and ranking (no vector store by design), how gbrain,
    cognee, LightRAG, graphrag, HippoRAG (personalized PageRank
    retrieval) rank, and what code-search products publish about
    ranking signals (Sourcegraph/zoekt BM25F + file rank).

## Suggested method

Parallel studies under `studies/2026-08-26-glean/`, one file each, every
one citing refreshed reference checkouts by commit and public docs by
URL; executed experiments on the Docker legs for the engine matrix and
on the in-memory backend for the merge simulation; one study written
with no access to this brief. Then one memo, then an ADR, then a spec.

## Study set (refreshed 2026-08-26; license verified)

Existing, refreshed to upstream default: graphify (`v8` @ 43d54ac,
Apache-2.0 — moved to `Graphify-Labs/graphify`, relicensed from MIT),
gbrain @ 872c3d6, zoekt @ a9206004, codesearch, LightRAG @ 812f2d5d,
graphrag @ f40e9a2, cognee @ 690c0ec02, graphiti @ 993e081, letta @
4511fa0bc, mem0 @ 39bc023, memori, MemOS, HippoRAG @ 2f52a86, KAG,
youtu-graphrag, sqlalchemy @ 0770f6e96, sqlite, postgres, langchain @
43bed06205, networkx @ cfc6b79, rustworkx @ e02dc7ce, scip, strwythura.

New shallow clones (all permissive): ranx (MIT), bm25s (MIT), pgvector
(PostgreSQL), pgvector-python (MIT), sqlite-vec (Apache/MIT), tantivy
(MIT), lucene (Apache), neural-search (Apache; OpenSearch's hybrid
normalization processor), lancedb (Apache), fastembed (Apache),
model2vec (MIT), llama_index (MIT), haystack (Apache), pyserini
(Apache), openai-python (Apache).

Refused under the license rule and deleted: OpenViking (AGPL-3.0),
meilisearch (MIT + BUSL-1.1 mixed), PyClick (GPL),
sourcegraph-public-snapshot (enterprise license), mariadb-docs (no
license file). Those projects are studied through public docs only.
