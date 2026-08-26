# glean, designed from first principles: an unconstrained proposal for ranked search in vfs

- **Status**: research memo — a design proposal, written blind to any
  requirements list (the author did not read the 2026-08-26 glean brief
  or its sibling studies, by instruction). Commits the project to nothing;
  input to the decide stage.
- **Date**: 2026-08-26
- **Owner**: Clay Gendron (memo drafted in-session by a search/IR engineer
  persona)
- **Question**: given ADR 007 (one fused `glean(query, limit, paths)` verb,
  no strategy selector), the live schema (`entries`, `content`, `chunks`
  with an `embedding` column, `edges`, gram postings/epochs), two audiences
  (agents over MCP; ETL writing 10k-file batches), five production engines
  plus SQLite, and mounts — what should ranked search *be*?
- **Evidence gathered**: (a) the live tree (paths cited below, at
  `5cfe1ef` on `main` plus the session's uncommitted working-tree edits
  to `dialects.py`/`grep.py`/`indexing.py`); (b) a source-level study of lucene `091a987`,
  tantivy `266a6c4`, bm25s `a213158`, zoekt `a9206004`, codesearch
  `b34f2a0`, pyserini `71072b4`, ranx `7363db0`, llama_index `d802122`,
  haystack `71b0ee6`, lancedb `2fbf6d6`, OpenSearch neural-search
  `972d698`, pgvector `e48241b`, sqlite-vec `04d28bd`, HippoRAG `2f52a86`,
  graphify `43d54ac` (branch `v8`), model2vec `280b341`, fastembed
  `c48247f`; (c) engine documentation and papers on the web (URLs inline);
  (d) two executed experiments on this machine (§12; scripts in the
  session scratchpad, ephemeral — the operative numbers are carried here).
  Prior art is cited and described only; nothing is copied.

---

## 0. The design in one page

**Rank chunks, answer with entries.** The retrieval unit is the semantic
chunk vfs already stores (`chunks`: 2 KB structure-aware pieces with line
ranges, ADR 036/048). Every signal scores chunks; the answer is the entry,
carrying its best-scoring regions as `Match` rows. Files are what an agent
reads next; regions are what it needs to read *first*.

**Two query-dependent signals, one query-independent prior.**

| signal | what it is | where it lives | where it is computed |
|---|---|---|---|
| **L** lexical | BM25 over chunk text, plus a BM25F-weighted path/name field | `chunk_terms`, `entry_terms`, `terms` (§3) | one aggregated SQL statement per glean, on every engine (§4.2) |
| **V** vector | cosine over per-chunk embeddings in a named *space* | `spaces`, `chunk_vectors` (packed float32, native type where the engine has one) | native kNN where the dialect declares a distance function; otherwise fetched and scored exactly in numpy, bounded by a scan budget with a disclosed lexical-gated fallback (§4.3) |
| **P** prior | PageRank over typed non-`fs` edges | `entries.rank` | reindex (§7); applied as a bounded multiplicative boost (§5.1) |

**No engine full-text search, anywhere.** Postgres `ts_rank` has no IDF,
MySQL's is TF·IDF² with no length normalization and a 3-char token floor,
SQL Server's RANK is "unimportant across queries", Oracle's SCORE is
collection-relative 0–100 (§13.1). Five tokenizers and five score scales
cannot fuse into one ranking. vfs owns one tokenizer (Rust engine + pure
reference, byte-identical like grams), one scorer, one set of statistics
per mount, and the ranking is the same on every engine.

**Fusion is reciprocal-rank fusion, k = 60, normalized to [0, 1].**
Inside a mount, L and V ranked chunk lists fuse by RRF; the fused chunk
score is divided by the best attainable sum so 1.0 means "rank 1 in every
signal this mount has". Entry score = max over its chunks × prior boost.
Across mounts the router keeps its existing `Result.top(limit)` — scores
are now genuinely comparable because every mount emits the same bounded
scale, and a mount missing a signal says so in a coverage warning rather
than being re-ranked by the router (§5.2).

**Embeddings enter through one injected object.** `Embedder` — a
protocol with `space` (name, dimension, metric) and one async
`embed(texts, *, kind="document"|"query")` — is handed to the storage at
construction. No embedder means lexical-only glean, still a capable
`SupportsGlean` backend, with the trait `glean_signals="lexical"`. The
mount's `spaces` row pins model name and dimension so a different model
can never write into an existing space silently (§8).

**Reindex computes everything derived** (chunks → term postings → vectors
→ prior → statistics), batch-wise, resumable per batch, off the event
loop, under the existing single-runner lease. Writes stamp nothing new
(§7). glean serves *only* indexed state; unlike grep it has no scan-side
overlay — it discloses the count of not-yet-indexed entries in scope
instead (§6).

**Not built**: engine FTS integration, ANN indexes beyond the pgvector
path already scaffolded, positional/phrase postings, rerankers, LLM query
rewriting, learned weights, per-scope IDF, recency boosts, a `mode`
parameter, centrality-as-a-query (§9). **Measured first**: a 200-query
judged eval over a code corpus and a prose corpus; latency at 30k/300k/3M
chunks on SQLite, Postgres and SQL Server; index bytes per chunk; reindex
throughput; sign-bit prefilter recall on *real* embeddings (§10).

---

## 1. What the tree already decided, and what it leaves open

Read before designing (the load-bearing facts):

- The verb is fixed: `glean(query, *, limit=10, paths=(), observations=None,
  columns=None, user_id=None)` (`src/vfs/base.py:1252-1285`); the router
  fans out by scope, passes `query`/`limit` through opaquely, merges, and
  re-applies `limit` with `Result.top()` — a sort by raw `score`
  (`base.py:2635-2650`, `src/vfs/results/envelope.py:580-586`). ADR 007
  records "re-fusing at the router" as a road not taken and calls
  cross-mount scores "only loosely comparable". §5.2 makes them comparable.
- `Match` is already glean-shaped: `start`/`end` line bounds, `match=None`
  "when the whole region matched, as in a glean chunk hit", per-region
  `score`, with `Observation.score` as the max across regions
  (`src/vfs/models/entry.py:334-352`). The result model needs no new field.
- Chunks are semantic-only by law (ADR 036 §2) and reindex-side by law
  (ADR 048 §1): `chunks(id, entry_id, chunk_index, line_start, line_end,
  content_hash, encoded, embedding, content)` (`src/vfs/models/rows.py:570-585`).
  `chunks.encoded` is a vestige of the pre-ADR-036 gram grain; §3 reuses
  the slot. `embedding` is a single JSON-text column, one space per mount.
- The dialect doctrine: declare only what SQLAlchemy takes no position on;
  unknown engines get the conservative floor; every `IN` list and bulk
  statement chunks by `membership_budget` (`dialects.py:30-140`, CLAUDE.md).
- Edges are ULID triples with `weight`/`distance`, both directions
  indexed (`rows.py:589-603`); parent→child edges are materialized with
  `edge_type='fs'` (ADR 018 §5). `mkedge` is stubbed; the graph verb's
  analytics are "index-time data feeding glean's graph signal" (ADR 007).
- The 2026-07-25 study already priced the vector floor: JSON-text vectors
  are honest to ~10k per query scope, packed float32 3–4× better, and
  community MySQL can compute no distance server-side at all
  (`studies/2026-07-25-multimodal-storage/vector-portability.md` §2, §4).
  §12.2 re-measures and sharpens: the JSON penalty is >1,000×, not 3–4×.
- The 2026-08-17 storage memo measured chunk-granularity nomination for
  grep and parked it (`2026-08-17-search-storage-organizations.md` §2).
  That verdict is about *grep's* fetch profile; it does not bind glean,
  whose whole point is that chunks are the ranking unit.

Open, and settled here: what to index (§2), where each stage runs (§4),
how to fuse (§5), the payload (§6), the pipeline (§7), the embedding seam
(§8).

---

## 2. Signals: what to index and why

### 2.1 The ranking unit is the chunk; the answer is the entry

Every studied hybrid system ranks passages, not files (Anthropic's
contextual-retrieval evaluation is top-20 *chunks*; llama_index and
haystack fuse `Node`/`Document` objects that are chunks; zoekt scores
lines/chunks and then files, `index/score.go:42-44, 302-352`). The reason
is not fashion: a 2 KB chunk is the largest unit an embedding model
represents faithfully and the smallest unit an agent can act on without
re-reading. vfs stores exactly that unit, keyed by `(entry_id,
chunk_index)` with line ranges — so the entry aggregation and the region
payload come free.

Entry score = **max** over its chunks (zoekt: file score is the max
fragment score plus tiebreakers; llama_index `simple` mode keeps max per
node). A multi-hit bonus is deliberately *not* in v1 — it is listed as
the first thing to measure (§10.1), because the two obvious formulas
(noisy-OR, `max + λ·Σrest`) both over-reward long files with many weak
hits and neither has evidence behind it.

### 2.2 Signal L — BM25 over chunks, BM25F over the path

**Why BM25 and not TF·IDF or engine ranking.** Every serious engine in
the study converges on the same scorer: Lucene (`BM25Similarity.java:122`,
k1 = 1.2, b = 0.75, `idf = log(1 + (N − n + 0.5)/(n + 0.5))` at `:138-140`),
tantivy (`src/query/bm25.rs:8-9, 52-56`), bm25s (`scoring.py:115-130,
190-195`), SQLite FTS5 (`bm25()`, k1/b hard-coded), SQL Server's
FREETEXTTABLE (Okapi k1 = 1.2, b = 0.75). The non-negative Lucene idf is
the right one for a corpus where a query term may appear in most chunks
(`return`, `error`) — Robertson's idf goes negative there and bm25s
clamps it.

**Constants.** k1 = 1.2, b = 0.75 as the Lucene/tantivy/FTS5 default;
pyserini shows the tuned optimum moves per corpus (0.9/0.4 for Anserini's
default, 0.82/0.68 on MS MARCO passage — `pyserini/search/lucene/_searcher.py:583`,
`docs/experiments-msmarco-passage.md:115`), so k1/b are backend-tunable
constants, never public parameters, and §10.1's eval is where they get
set.

**Tokenizer.** One code-aware tokenizer, in `crates/vfs-core` with a pure
Python reference pinned byte-identical (the gram doctrine, ADR 039):

- split on any non-alphanumeric byte; emit the whole identifier **and**
  its `snake_case` / `CamelCase` / digit-run sub-tokens (`drm_gem_object_put`
  → itself + `drm`, `gem`, `object`, `put`), so a natural-language query
  ("gem object") reaches code and an identifier query stays exact;
- lowercase (the same Turkic pre-fold as `code_grams.py` so the two
  streams agree on case);
- token length 2..64 (tantivy's default pipeline is `SimpleTokenizer` +
  `RemoveLongFilter(40)` + `LowerCaser`, `tokenizer_manager.rs:61-81`);
- **no stemming, no stopword list**. Stemming is off by default in
  tantivy and Lucene's `StandardAnalyzer` handles code badly; stopwords
  are handled by df, not by a language list (§4.2's term budget), which
  is what makes the tokenizer language-neutral. bm25s ships an English
  stopword list *on* by default (`tokenization.py:152-155`) — a prose
  assumption vfs cannot make.
- [NEEDS CLARIFICATION: CJK — per-codepoint bigrams (the FTS5 `trigram`
  / ICU approach) or leave CJK bodies to the vector signal? The tokenizer
  above yields one token per CJK run, which is useless for lexical
  recall.]

**Fields.** Two: chunk *content* and the entry's *path* (every path
segment tokenized as above, so `auth/session_store.py` yields `auth`,
`session_store`, `session`, `store`, `py`). BM25F-style: the path field's
contribution is a second BM25 sum with its own length normalization and
field weight `w_path` (default 2.0, tunable), added to the chunk's
content score. Precedent: Lucene's `CombinedFieldQuery` (weighted tf into
one saturation, `CombinedFieldQuery.java:284-312`), zoekt's filename and
symbol boosts (`contentprovider.go:588-609`: basename match 7,000 vs word
match 500 — the strongest query-dependent signal it has), Sourcegraph's
move to BM25F over filename+content ("Keeping it boring and relevant with
BM25F", https://sourcegraph.com/blog/keeping-it-boring-and-relevant-with-bm25f).
Symbols are *not* a field in v1: vfs has tree-sitter spans but no symbol
extraction; noted under §9 as the obvious next field.

### 2.3 Signal V — embeddings in named spaces

**Storage.** A `spaces` registry (one row per embedding space per mount:
name, model name, dimension, metric, created_at) and a `chunk_vectors`
sidecar keyed `(space_id, chunk_id)`. This replaces `chunks.embedding` —
the 2026-07-25 memo's recommendation (§4 Q8: "space-keyed embeddings
store with row-level model identity"), and the only shape under which a
second space (a multimodal model, a re-embedding with a newer model) can
coexist with the first. Vector bytes are **packed little-endian float32**
in the portable column; where the dialect has a native type the column
takes it through the `VectorType.load_dialect_impl` pattern already in
`src/vfs/models/vector.py:868-871` (pgvector `vector(N)`; Oracle's in-tree
SQLAlchemy `VECTOR`; SQL Server's JSON-over-pyodbc protocol, which the
study found *is* the documented client path).

**Why exact cosine is the floor and ANN is an upgrade.** §12.2: exact
top-50 over 500,000 × 768 float32 in numpy is **51 ms** once the vectors
are in memory; the cost is data motion (1.5 GB for that scan), not
arithmetic. glean's `paths` scope is the lever that keeps scopes in the
tens of thousands, where the floor is 1–10 ms of math plus a bounded
fetch. Above the scan budget the floor does not silently truncate — it
degrades to lexical-gated rescoring (§4.3) and says so.

**Query embedding.** One embedder call per glean (`kind="query"` —
asymmetric models need the prefix: nomic's `search_query:` /
`search_document:`, https://huggingface.co/nomic-ai/nomic-embed-text-v1.5;
llama_index and haystack both split query and document embedding into
separate methods/components for this reason, `llama-index-core/.../base/embeddings/base.py:133, 272`,
`haystack/components/embedders/types/protocol.py:10-45`), memoized in a
small LRU keyed `(space, query)`.

### 2.4 Signal P — a graph prior, not a graph query

Sourcegraph's ranking is the clearest public evidence that a
query-independent importance score over the code graph is a strong
signal ("PageRank is a measure of code reuse",
https://about.sourcegraph.com/blog/new-search-ranking). HippoRAG goes
further — Personalized PageRank at query time over an entity/passage
graph with dense scores as seeds (`HippoRAG.py:2084-2100`, damping 0.5,
`passage_node_weight` 0.05) — and that is precisely what vfs should *not*
do in v1: a query-time PPR is a whole-graph iteration per call, and its
benefit is documented on multi-hop QA benchmarks, not on agent file
search.

The prior: PageRank (damping 0.85, weighted by `edges.weight` where set)
over the typed edge graph **excluding `edge_type='fs'`** (the materialized
hierarchy is a tree; PageRank over a tree just rewards depth), computed
at reindex, stored as `entries.rank`. Applied as a bounded multiplicative
boost (§5.1). Zero non-fs edges → every rank equal → boost is the
identity; the signal costs nothing until a mount has a real graph. Lucene
does the same thing structurally (`FunctionScoreQuery.boostByValue`,
multiplicative, bounded so pruning stays sound, `FunctionScoreQuery.java:84-85, 268`).

### 2.5 Not indexed

- **Positions / phrases.** The 2026-08-17 memo measured positional
  postings at 15.3× the index (§5); Lucene needs them for phrase queries,
  vfs has `grep` for exact strings. A phrase in a glean query is just
  its terms.
- **Recency.** Agents ask for relevance; `updated_at` is on every row for
  the caller to sort by. A recency prior is a product decision to measure
  later, not an assumption to bake in.
- **Symbols, headings, comments as fields.** Real, valuable, and
  requires extraction machinery that does not exist — §9.
- **Per-scope statistics.** IDF is per mount. bm25s masks after scoring
  with corpus-level idf (`__init__.py:582-612`); every engine studied does
  the same. A scope-local idf would need a second aggregate per query
  for a benefit nobody has demonstrated.

---

## 3. Schema additions (one mount, `build_vfs_tables`)

All keyed by chunk or entry identity; all regenerable; all die with their
owner in the same delete statements. `SCHEMA_FORMAT_VERSION` 6 → 7.

```
terms          (id INT PK, term BytewiseString(64) UNIQUE, df INT)
chunk_terms    (term_id INT, chunk_id BIGINT, tf SMALLINT)   PK (term_id, chunk_id), index (chunk_id)
entry_terms    (term_id INT, entry_id ULID, tf SMALLINT)     PK (term_id, entry_id), index (entry_id)
spaces         (id SMALLINT PK, name String(128) UNIQUE, model String(255), dimension INT,
                metric String(16), created_at)
chunk_vectors  (space_id SMALLINT, chunk_id BIGINT, vector VectorType(space))  PK (space_id, chunk_id)
chunks         + length SMALLINT (token count)        ; `encoded` renamed `lexed` (the lexical dirty flag)
entries        + rank REAL (PageRank prior; NULL = unranked)
meta           + lexical_chunks INT, lexical_avgdl REAL, lexical_generation String(32)
```

Sizing, measured (§12.1): 4,681 C/H files, 55.3 MB → 29,711 chunks,
311,001 terms, 3,345,316 postings; **2,156 B per chunk, 1.16× the
content bytes** in SQLite including the term dictionary and both
indexes. Proportionally, the 93,760-file linux store (726,817 chunks) is
~1.6 GB of lexical index beside 1.22 GB of content — heavier than the gram
index (141.5 MB) because postings carry a per-chunk tf, and the price of
ranking rather than nominating. Byte-per-chunk is the number to watch;
`(term_id, chunk_id)` as a composite PK on a clustered engine is already
the compact form (Lucene/tantivy store 1 byte per doc per field for the
norm; `chunks.length` as SMALLINT is the SQL equivalent).

`chunk_vectors` at 768 dims is 3,072 B per chunk per space (§12.2), so
one space roughly doubles the per-chunk footprint; the JSON-text column
it replaces was 16,921 B for the same vector.

---

## 4. Where ranking runs

### 4.1 The pipeline, per mount, per call

```
tokenize(query)                                  Python (engine seam), ≤ 32 terms
   │
   ├─ L: one SQL statement → top-N chunk ids + bm25          engine
   ├─ V: embed(query) → kNN (native) | fetch+numpy (floor)   embedder, then engine or Python
   │
   fuse (RRF, normalize) → chunk scores → entry = max         Python
   × prior boost, clip → top-limit entries                    Python
   fetch regions + projected columns for those entries        engine (one IN-list fetch)
```

N (the per-signal candidate depth) = `max(10 × limit, 100)`. Over-fetch
is universal (Elasticsearch `rank_window_size`, pyserini `depth=1000`,
Anthropic's top-20) and here it has a second job: chunks collapse into
entries, and a top-10 of entries can need far more than 10 chunks.

Everything the backend does stays inside the read discipline grep set:
one session, SELECTs only, retry on stale snapshot, budgets that truncate
with a warning record rather than fail (`grep.py` module docstring).

### 4.2 Signal L runs in the engine — one portable statement

```sql
WITH q(term_id, idf) AS (SELECT :t1, :idf1 UNION ALL SELECT :t2, :idf2 ...)    -- ≤ 32 arms
SELECT c.id AS chunk_id,
       SUM(q.idf * p.tf * (K1 + 1) / (p.tf + K1 * (1 - B + B * c.length / :avgdl)))
     + COALESCE(pn.path_score, 0) * :w_path                          AS score
FROM chunk_terms p
JOIN q            ON q.term_id = p.term_id
JOIN chunks c     ON c.id = p.chunk_id
JOIN entries e    ON e.entry_id = c.entry_id
LEFT JOIN ( SELECT n.entry_id, SUM(q.idf * n.tf * (K1+1) / (n.tf + K1*(1-B+B*e2.name_len/:avg_name_len)))
              AS path_score FROM entry_terms n JOIN q ON q.term_id = n.term_id ... GROUP BY n.entry_id ) pn
       ON pn.entry_id = e.entry_id
WHERE e.deleted_at IS NULL AND e.kind IN (content kinds) [AND <scope predicate on e.path>]
GROUP BY c.id, pn.path_score
ORDER BY score DESC
LIMIT :n
```

Why in the engine and not "fetch postings, score in Python": §12.1
measured both on the same SQLite store — **1.3–9.5 ms in SQL vs 2.8–21 ms
in Python** for the same five queries, and the Python path ships the
postings over the wire (25,848 rows for a five-word query) where the SQL
path ships 50 rows. On a networked engine the gap widens by the
round-trip cost of moving postings. Aggregation, ordering and LIMIT are
what SQL engines are good at; an engine-side top-N is also the shape that
lets a scope predicate prune postings *before* scoring.

Portability notes, each a declared fact rather than a hope:

- The idf table arrives as a `UNION ALL` of literal selects, not a
  `VALUES` table — `DialectProfile.values_join` already records that
  engines disagree on `VALUES` as a join source (`dialects.py:86-143`),
  while `UNION ALL SELECT ... FROM DUAL` compiles everywhere through
  SQLAlchemy. 32 arms sits far inside `expression_depth_budget`.
- The statement carries ≤ 32 term binds + a handful of constants — no
  `IN` list grows with anything the caller controls. Scope predicates
  reuse glob's sargable `LIKE` prefilter on `path` (`reads.py`), or the
  rows-in-hand entry-id list chunked by `membership_budget` (ADR 034) when
  the caller passed `observations`.
- Float summation order inside `GROUP BY` is engine-specific, so scores
  are *not* byte-identical across engines; the parity test pins the
  top-N **set** and the order up to a score tolerance (1e-6 relative),
  not the bytes. This is a declared exception to grep's byte-identical
  law, of the same kind as ADR 048's chunking exception.
- **Term budget.** Query terms are sorted by df ascending and included
  while the running Σdf stays under `LEXICAL_POSTING_BUDGET` (proposed
  2,000,000 rows), with the three rarest always in. A dropped term
  (`return`, `the`) is a warning-severity `vfs.glean.terms_dropped` record
  naming it. This is grep's posting-byte budget transplanted; it is what
  replaces stopword lists, and it bounds the statement's work on any
  corpus. Lucene and tantivy bound the same cost with block-max WAND
  (`MaxScoreBulkScorer.java:28-43`, `block_wand_union.rs:7-42`), which
  needs per-block impacts baked into postings — a storage format SQL
  rows cannot express; the budget is the honest SQL analogue.

### 4.3 Signal V — native where declared, exact floor otherwise, gated above budget

Two new `DialectProfile` fields (facts SQLAlchemy takes no position on
for three of the five engines, per the 2026-07-25 study §4):

- `vector_distance: Literal["none", "exact", "ann"]` — sqlite `none`,
  mysql `none` (community MySQL has the type and no distance function,
  https://dev.mysql.com/doc/refman/9.7/en/vector-functions.html), mssql
  `exact` (`VECTOR_DISTANCE` GA; `VECTOR_SEARCH`/DiskANN preview-gated,
  https://learn.microsoft.com/en-us/sql/sql-server/ai/vectors?view=sql-server-ver17),
  oracle `ann` (in-tree SQLAlchemy `VECTOR` + `VectorIndexConfig`),
  postgresql `ann` **only after a first-touch probe finds the `vector`
  extension** — otherwise `none`. The generic floor claims `none`.
- `vector_dimension_cap: int | None` — pgvector index 2,000, SQL Server
  1,998, MySQL 16,383, Oracle 65,535; a space over the cap is stored but
  refused for the native tier with a classified first-touch error.

Three tiers, all producing the same `(chunk_id, cosine)` top-N list:

1. **Native** (`exact`/`ann`): `ORDER BY distance(vector, :q) LIMIT n`
   with the scope predicate in the same statement. pgvector's own docs
   warn that HNSW post-filters and returns fewer rows unless
   `hnsw.iterative_scan` is on (`pgvector/README.md:450, 480-495`) — the
   backend sets `SET LOCAL hnsw.iterative_scan = relaxed_order` per
   session where the extension is 0.8+, and verifies the row count.
2. **Floor** (`none`, scope ≤ `VECTOR_SCAN_BUDGET` = 50,000 chunks):
   fetch `(chunk_id, vector)` for the scope in `membership_budget`
   batches, score each batch in numpy, keep a running top-N — memory is
   one batch plus N, not the scope. 50,000 × 3 KB = 150 MB on the wire,
   ~5 ms of math (§12.2); the wire is the ceiling, disclosed in the
   docstring per the no-designed-cap rule.
3. **Lexical-gated** (`none`, scope over budget): the vector signal
   rescores only the L top-N (N = 10 × limit, min 100) chunks. Recall against
   pure-vector is lost for chunks with no lexical overlap, and the call
   carries a warning `vfs.glean.vector_gated` saying so. This is the
   honest answer for MySQL and unknown engines at scale; it is also
   exactly the point where an operator should install pgvector or move
   to Oracle, and the warning says that too.

Sign-bit (Hamming) prefiltering, the study's §3.3 upgrade, is **not**
in the design until measured on real embeddings: on isotropic random
vectors §12.2 found recall@50 of 0.82 at 10k and **0.40 at 100k** at 20×
oversampling. Random vectors are the worst case (no structure to
preserve), so the number is a warning, not a verdict — §10.5.

### 4.4 Fusion and aggregation run in Python, in the backend

The lists are small (2 × N rows) and the arithmetic is trivial; nothing
here justifies a round-trip. The router never sees signals (ADR 007).

---

## 5. Fusion

### 5.1 Inside a mount

**RRF, k = 60**, over the L and V chunk lists:

```
rrf(chunk)   = Σ_{s ∈ signals present, chunk ∈ list_s}  1 / (k + rank_s(chunk))      rank 1-based
score(chunk) = rrf(chunk) / ( |signals present| / (k + 1) )                          ∈ (0, 1]
score(entry) = max_{chunk ∈ entry} score(chunk) × boost(entry),  clipped to 1.0
boost(entry) = 1 + β · clip(log1p(rank / mean_rank), 0, 1)        β = 0.15; identity when rank is NULL or uniform
```

Why RRF and not min-max weighted sum: it is the field's no-training
default — Cormack, Clarke & Büttcher 2009 fixed k = 60 in a pilot and
found "the choice was not critical" (Table 1: MAP .2072 at k=0, .2145 at
k=60, .2098 at k=500; http://cormack.uwaterloo.ca/cormacksigir09-rrf.pdf);
ranx `rrf.py:39`, llama_index `fusion_retriever.py:122-134`, lancedb
`rrf.py:15-36`, pyserini `_base.py:30-56`, OpenSearch
`RRFNormalizationTechnique.java:44-45`, Elasticsearch's RRF retriever
(`rank_constant` 60) and Weaviate's `rankedFusion` all use 60. The
counter-evidence is real and recorded: Bruch, Gai & Ingber (TOIS 2023,
https://arxiv.org/abs/2210.11934) show a tuned convex combination beats
RRF in- and out-of-domain and that RRF is sensitive to k; Weaviate moved
its default to `relativeScoreFusion` in v1.24 citing ~6% recall
(https://weaviate.io/blog/hybrid-search-fusion-algorithms). The
distinction is *tuning data*: convex combination needs labeled queries to
set α per corpus; RRF does not. vfs ships to corpora it has never seen.
The eval in §10.1 is where the project earns the right to switch — and
the fused-score seam is where it would switch, invisibly to the verb.

Off-by-one, decided: rank is 1-based (Cormack, Elasticsearch, pyserini
via TREC ranks); haystack uses k = 61 with 0-based ranks to mean the same
thing (`haystack/utils/misc.py:164`). Pinned by a test.

The normalization to (0, 1] is the one addition to textbook RRF and it
exists for the router: rank 1 in every present signal scores exactly
1.0, rank 1 lexical + rank 10 vector scores (1/61 + 1/70)/(2/61) ≈ 0.94,
and a lexical-only mount's rank-1 also scores 1.0 — see §5.2 for why
that is the intended policy.

The prior is multiplicative and bounded (β = 0.15 → at most +15%), never
a third RRF list: as a ranked list it would inject the most-referenced
files into every query regardless of relevance. Zoekt reserves score
*bands* for the same reason — static rank breaks ties only
(`score.go:343-352`: `1e7 × score + 100 × repoRank + 10 × docOrder`).

### 5.2 Across mounts — the router keeps `top(limit)`, and the scale makes it honest

Today `_cap_rows` sorts the merged rows by `score` (`base.py:2635-2650`).
With every backend emitting the §5.1 scale this is the right merge: each
mount's best hit is ≤ 1.0, its tenth is whatever its signals said, and
the router interleaves by that. Two properties fall out:

- **A mount is never punished for having fewer signals.** A lexical-only
  mount (no embedder) competes on its own best; a two-signal mount's
  hits that are strong in only one signal score ≈ 0.5 — which is
  correct, they *are* weaker evidence. The gap in coverage is reported
  (§6), not hidden by rank interleaving.
- **Re-fusing by rank at the router is rejected** (ADR 007's road not
  taken, and this memo agrees): RRF across mounts would interleave a
  10-row answer from a tiny mount 1:1 with a 10-row answer from the
  main corpus regardless of quality; and the router cannot know a
  mount's signal count. Score-normalized merge needs exactly one
  promise from backends — the scale — and the `SupportsGlean` docstring
  should state it.

`limit` stays as it is: per-entry bound and merged bound, entries not
chunks.

---

## 6. What comes back to the agent

An `Observation` per entry, `populated` stamped like every other read
(`reads.py:84-100`), default projection:

| field | value |
|---|---|
| `path`, `kind`, `ext`, `size_bytes`, `updated_at`, `version` | entry facts, from the one post-fusion fetch |
| `score` | §5.1 scale, `[0, 1]` |
| `matches` | the entry's top ≤ 3 chunks by fused score, each `Match(start=line_start, end=line_end, match=None, content=<chunk text>, score=<chunk score>)` |
| `content` | **only when `columns` asks** — the region is the preview; the file is one `read` away |
| `in_degree` / `out_degree` | populated when the prior contributed (cheap, already query fields) |

Three chunks × ~2 KB is ~6 KB per row, 60 KB for a default `limit=10` —
what an agent can actually read before choosing. Anthropic's finding that
top-20 chunks beat top-5/10 in the prompt
(https://www.anthropic.com/news/contextual-retrieval) argues for regions
over whole files: 20 × 2 KB fits; 20 files do not.

Errors and warnings ride the envelope's structured channel
(`ResultError`, `envelope.py:76-105`), never prose:

| record (`kind`, `data` keys) | when |
|---|---|
| `vfs.glean.coverage` warning, `data={"vfs.signals": ["lexical"]}` | a mount in the fan-out has no vector space (no embedder), or its space is empty |
| `vfs.glean.stale` info, `data={"vfs.unindexed": n}` | `n` entries in scope with `NOT chunked` or `NOT lexed` — one cheap `COUNT` per call; glean has no scan overlay |
| `vfs.glean.terms_dropped` warning, `data={"vfs.terms": [...]}` | §4.2 term budget dropped query terms |
| `vfs.glean.vector_gated` warning, `data={"vfs.scope": n, "vfs.budget": b}` | §4.3 tier 3 ran |
| `invalid` error | empty query after tokenization; embedder refused the query |
| `backend_unavailable` warning (demoted under the zero-progress rule) | the embedder raised for this call — the call still answers lexically |

The `traits()` map (`backend.py:124-140`) grows `glean_signals`
(`"lexical"` / `"lexical,vector"`), `glean_vector_tier`
(`native`/`floor`/`gated`) and `embedding_space` (`name:dimension`), so
an MCP host can describe each mount's search honestly before the first
call.

---

## 7. The reindex pipeline

Extends `_reindex_phases` (`backend.py:515-585`). Every phase is its own
writer transaction, CPU hops through the offload pool, the lease
heartbeats between phases, and a lost lease stops at the next boundary —
nothing new in the control shape. Phases, in order:

| phase | reads | computes (off-loop) | writes | idempotent when |
|---|---|---|---|---|
| A chunk (exists) | dirty entries | split | `chunks` rows; flips `chunked` | fingerprint-skip |
| B grams (exists) | `indexable` entries | postings | epoch rows; flips `encoded` | epoch fingerprint |
| **C lexical** | chunks with `NOT lexed`, batched by content bytes | tokenize (Rust), per-chunk tf, path tf per entry | `terms` (upsert new terms), `chunk_terms`, `entry_terms`, `chunks.length`; df deltas; flips `lexed` per batch | nothing `NOT lexed` |
| **D vectors** | chunks with no `chunk_vectors` row for the mount's space, batched by the embedder's batch size and a byte budget | `embed(texts, kind="document")` | `chunk_vectors`; one commit per batch | anti-join empty |
| **E prior** | `edges` where `edge_type <> 'fs'` | PageRank (20 iterations, damping 0.85) | `entries.rank` in chunked `UPDATE ... VALUES` batches | edge count and max edge id unchanged since last run (stamped in meta) |
| **F stats** | — | `lexical_chunks`, `lexical_avgdl` by one aggregate | `meta` | always cheap |
| segments (exists) | | | | |

Design points that bind:

- **Deletes cascade by chunk id, set-based.** Phase A's re-split already
  deletes `chunks` by `entry_id IN (...)`; C and D rows are deleted first
  by `chunk_id IN (SELECT id FROM chunks WHERE entry_id IN (...))`
  (the correlated-subquery form is portable; the MySQL-family
  self-referential-delete restriction does not apply across tables).
  Sweep's `_purge_subtree` gets the same two arms. Trashed entries keep
  their rows and are excluded at query time by the liveness join — the
  restore contract rides free.
- **df is maintained by deltas, recounted on a generation bump.** Per
  batch, Python holds a `Counter[term_id]` of new (term, chunk) pairs
  and applies chunked `UPDATE terms SET df = df + :d`; a delete batch
  subtracts. A full `INSERT ... SELECT term_id, COUNT(*)` recount runs
  only when `lexical_generation` changes (tokenizer or constant bump) —
  it is O(postings) inside the engine, never in Python.
- **The embedding phase is resumable and failure-tolerant.** Each batch
  commits; a crashed run loses one batch; a raising embedder stops phase
  D with a classified warning on the reindex `Result` and the lexical
  index is still published. Rate limits and retries are the embedder's
  business (haystack and llama_index both keep retry/rate-limit inside
  the embedder object, `base.py:95-100`). Cost is disclosed, not hidden:
  the linux store's 726,817 chunks at ~500 tokens each is ~360M tokens
  per full embed — the number an operator needs before choosing a
  hosted model.
- **The tokenizer is engine work.** §12.1 tokenized 55 MB in 14.5 s of
  pure Python (3.8 MB/s); at linux scale that is ~5 minutes on the
  reindex wall, against a ≤ 60 s target (ADR 048). The Rust engine with
  rayon is the plan of record (the gram extractor's profile: same
  shape, same seam); the pure reference stays for the fallback leg and
  the parity test.
- **Residency, honestly.** Phase C holds one batch of bodies and its tf
  map; phase D one batch of texts and vectors; phase E the whole edge
  list and one float per entry (the same corpus-width profile the
  segment pass already declares, `segments.py` docstring). No cap; the
  future direction for E is a Rust or SQL-iterated PageRank if a mount's
  graph outgrows memory.

Nothing moves to the write path. A write stamps `chunked=False` today
and that already implies "not lexed, not embedded" downstream (chunk
rows are replaced wholesale). ETL's 10k-batch profile is untouched.

---

## 8. Embeddings without a model of our own

vfs must never import torch, call a network, or pick a model. The seam:

```python
class EmbeddingSpace(NamedTuple):
    name: str          # "text-embedding-3-small:256", "potion-base-8M"
    dimension: int
    metric: Literal["cosine", "dot", "l2"] = "cosine"

class Embedder(Protocol):
    space: EmbeddingSpace
    batch_size: int                        # the batch the embedder wants; the phase respects it and a byte budget
    async def embed(self, texts: Sequence[str], *, kind: Literal["document", "query"]) -> list[list[float]]: ...
```

- **Injected at storage construction**: `DatabaseStorage(url=...,
  embedder=...)`. First touch compares `embedder.space` with the mount's
  `spaces` row: no row → insert; equal → proceed; different model or
  dimension → classified `invalid` refusal naming both. lancedb persists
  the embedding-function config in table metadata for exactly this
  reason (`embeddings/registry.py:91-145`); vfs persists only the
  identity, never a callable.
- **One method, one `kind` flag** rather than two methods: the
  query/document asymmetry is a property of the model and the flag
  makes it impossible to forget; symmetric models ignore it
  (lancedb's `TextEmbeddingFunction` collapses the two for symmetric
  models, `embeddings/base.py:210-227`).
- **Async, batched, no retries in vfs.** llama_index defaults
  `embed_batch_size` to 10 (`core/constants.py:8`), fastembed to 256
  (`text_embedding.py:160`); the phase takes the embedder's number and
  caps bytes.
- **Vectors are normalized on write** when `metric == "cosine"`, so the
  floor's dot product is the cosine and the native tiers use the
  cheapest operator (`<#>` / inner product).
- **Two adapters ship as optional extras, no model in core**: an
  OpenAI-compatible HTTP adapter (`vfs-py[openai]` already exists in
  `pyproject.toml`) and a model2vec adapter as the zero-infrastructure
  default — static embeddings, ~30 MB on disk, no torch, "up to 500×
  faster on CPU" than the sentence-transformer it distills
  (`model2vec/README.md:44, 136-138`; potion-base-8M distilled from
  bge-base-en-v1.5, `:166`). Its quality is below a transformer's; that
  is the trade a dev laptop makes, and the eval (§10.1) should quote
  both. Matryoshka-trained models (OpenAI text-embedding-3, nomic v1.5/v2)
  let a space declare a truncated dimension — 256 of 3,072 still beats
  ada-002 at 1,536 on MTEB
  (https://openai.com/index/new-embedding-models-and-api-updates/) —
  which is how a space stays under a 2,000-dim index cap without
  changing models.
- **Tests use a deterministic hashing embedder** (feature-hashed
  bag-of-tokens, L2-normalized) so the vector tier and fusion are pinned
  without a network or a model file.

---

## 9. What I would explicitly not build

1. **Engine full-text search as a tier.** Five tokenizers, five
   incomparable scales, no BM25 in Postgres core (§13.1). Even as an
   "accelerator" it would produce different rankings per engine, which
   is the one property the design refuses to give up.
2. **ANN indexes beyond what exists.** pgvector's HNSW path is already
   scaffolded (`NativeEmbeddingConfig`, `vector.py:733-745`); Oracle's
   comes free with SQLAlchemy's `VectorIndexConfig`. DiskANN on SQL
   Server is preview; pgvectorscale was already held
   (`2026-04-20-pgvectorscale.md`). Nothing else until a scope exceeds
   the floor in a real deployment.
3. **Positional postings, phrase queries, proximity scoring.** 15.3×
   the index for a feature `grep` serves exactly.
4. **A reranker (cross-encoder, LLM).** Anthropic's numbers say it is
   the biggest single win (2.9% → 1.9% failure) — and it is a *caller*
   concern: the agent has the regions, the model, and the budget. A
   `rerank` hook on the backend would be the thing to add, not a
   bundled model. Not in v1.
5. **Query rewriting / expansion** (llama_index's `num_queries=4` LLM
   fan-out). Same reason: the agent is the LLM.
6. **Learned or tuned fusion weights, per-mount k, per-corpus k1/b.**
   Constants until §10.1 produces evidence; then constants with a
   different value.
7. **Per-scope IDF, recency boosts, symbol/heading fields.** §2.5.
8. **A `mode` parameter, a `signals` parameter, a "vector only" flag.**
   ADR 007. Coverage is *reported* (§6), never *selected*.
9. **Query-time graph traversal (PPR) as part of glean.** HippoRAG's
   mechanism is real and expensive; `graph` is the verb for walking.
10. **Caching fused results.** The 2026-08-17 memo measured an 8.2%
    exact-repeat rate in agent searches; a query-embedding LRU is the
    only cache worth its invalidation story.

---

## 10. What to measure before committing

1. **A judged eval, two corpora, ~200 queries.** Corpus A: the
   `drivers/gpu/drm` subset (code, 29,711 chunks); corpus B:
   `context/` + `docs/` of this repo (prose, spec-driven). Queries:
   50 identifier lookups, 50 natural-language "where is X handled",
   50 conceptual (prose), 50 mixed. Judgments: LLM-labeled at the
   chunk level, 20% human-checked. Metrics: nDCG@10, recall@20 (the
   agent's real question), MRR. Arms: L only; V only (model2vec; one
   hosted model); RRF; RRF + prior; `w_path` ∈ {0, 1, 2, 4}; entry =
   max vs noisy-OR vs max+λΣ. This is the experiment that sets every
   constant in §5.1 and decides whether Bruch's convex combination is
   worth its tuning cost.
2. **Latency ladders** on SQLite, Postgres, SQL Server (the `db_test`
   containers) at 30k / 300k / 3M chunks: p50/p95 of the L statement
   for rare, common and budget-tripping queries; the V floor at scope
   sizes 1k / 10k / 50k; native kNN where available; end-to-end glean
   with the regions fetch. Statement counts per call (target ≤ 5).
3. **Index cost**: bytes per chunk for `chunk_terms` + `terms` on each
   engine (the §12.1 SQLite number is 2,156 B); reindex phase C
   throughput in chunks/s, pure vs Rust tokenizer; phase D throughput
   against model2vec locally and one hosted API.
4. **Cross-mount fairness**: two mounts, one lexical-only, one with
   vectors, shared eval queries — does the §5.2 policy surface the
   right mount's hits? Compare against router-side RRF to close ADR
   007's road-not-taken with numbers.
5. **Sign-bit prefilter recall on real embeddings** at 100k / 500k
   with 10×/20×/50× oversampling — the §12.2 random-vector result
   (0.40 @ 100k) must be re-run on model2vec and a transformer's
   vectors before tier 3 (§4.3) is allowed to become "Hamming-gated"
   instead of "lexical-gated".
6. **Staleness window**: median seconds from write to glean-visible
   under a reindex cadence of 60 s / 5 min / on-demand, measured on the
   ETL batch shape. This number is what the `vfs.glean.stale` record
   will be reporting in practice.

---

## 11. The three riskiest assumptions in this design

1. **That untuned RRF at k = 60 with equal weights, chunk-max entry
   aggregation, and a 2 KB chunk grain is good enough on both code and
   prose.** Bruch et al. say tuned convex combination is better and RRF
   is k-sensitive; Weaviate switched defaults and measured 6%. If §10.1
   shows RRF losing by more than a few points of nDCG@10 on either
   corpus, the fusion seam changes — the verb does not — but the
   normalized-score contract with the router (§5.2) must be preserved
   by whatever replaces it.
2. **That SQL-side BM25 stays interactive on networked engines at 3M+
   postings per common term.** §12.1 is SQLite on a laptop; a 5-word
   query touched 25,848 postings in 9.5 ms. A `return`-shaped term over
   a 726k-chunk corpus is ~500k postings, and the term budget (§4.2)
   is a blunt instrument: drop it and recall for "return error code"
   suffers; keep it and Postgres aggregates half a million rows per
   call. Lucene and tantivy solve this with impacts and block-max
   pruning that SQL rows cannot express. The mitigation to test is a
   per-term posting **tier** — store `chunk_terms` rows only for chunks
   whose tf is in the top X% for terms above a df threshold — which is
   lossy and must be measured before it is designed.
3. **That reindex-side embedding with an injected external model is
   operationally acceptable to both audiences.** An agent writes a file
   and expects to glean it; under this design it is invisible to glean
   until the next reindex, and the design's only answer is the
   `vfs.glean.stale` count. ETL pipelines writing 10k files then
   embedding 10k × ~5 chunks through a hosted API pay minutes and real
   money per batch, and a rate-limited API mid-phase leaves a half-
   embedded corpus that the vector signal ranks *against* (chunks
   without vectors are simply absent from V). If §10.6's staleness
   window is unacceptable, the fallback is a write-path *enqueue* (not
   embed) and a background embed loop — a topology the tree does not
   have yet (the reindex lease is single-runner, verb-invoked).

A fourth, structural, is worth naming: the design assumes the term
dictionary (`terms`) is per mount and shared across the mount's chunks
*and* paths. If two mounts are meant to be one search corpus, their idf
statistics differ, and the §5.2 normalization is what keeps that from
mattering — an assumption, not a proof.

---

## 12. Executed experiments

Apple Silicon laptop, Python 3.13 via `uv run`, numpy 2.4.2, SQLite
3.50.4. Scripts lived in the session scratchpad (`exp_lexical.py`,
`exp_vector.py`); ephemeral by policy, numbers carried here.

### 12.1 SQL-side BM25 on a real code corpus

Corpus: `~/Git/Repos/linux/drivers/gpu/drm` minus `amd/`, `.c`/`.h`
only — 4,681 files, 55.3 MB. Split into 2,048-char line-aligned chunks
(an approximation of `Chunk.split`'s recursive fallback), tokenized with
the §2.2 tokenizer in pure Python, stored as `chunks(id, path,
line_start, line_end, len)`, `terms(id, term, df)`, `postings(term_id,
chunk_id, tf)` `WITHOUT ROWID`.

| | value |
|---|---|
| chunks / distinct terms / postings | 29,711 / 311,001 / 3,345,316 |
| tokenize + split (pure Python) | 14.5 s (3.8 MB/s) |
| insert | 5.0 s |
| database size | 64.1 MB = **2,156 B/chunk = 1.16× content** |

Query latency, warm, top-50, Lucene idf, k1 = 1.2, b = 0.75. "SQL" is
the §4.2 statement shape (idf via `UNION ALL` CTE, `SUM ... GROUP BY ...
ORDER BY ... LIMIT 50`); "Python" fetches the raw postings for the same
terms and scores with numpy.

| query | postings touched | SQL | Python |
|---|---|---|---|
| `drm_gem_object_put` (identifier → 4 tokens) | 25,421 | 8.3 ms | 20.8 ms |
| `vblank interrupt handler` | 3,226 | 1.3 ms | 2.8 ms |
| `return error` | 21,666 | 7.9 ms | 17.0 ms |
| `atomic commit tail plane state` | 15,059 | 5.6 ms | 16.1 ms |
| `how does the display pipeline handle page flips` | 25,848 | 9.5 ms | 21.0 ms |

Reading: engine-side aggregation wins 2–3× on the same machine before
any network cost, and the cost is linear in postings touched (~0.35 µs
per posting in SQLite). `return` alone is 20,000 of the 21,666 postings
in row 3 — the term budget's target.

### 12.2 The portable vector floor

Random unit vectors, d = 768, float32, top-50 by dot product; sign-bit
Hamming prefilter = `packbits(x > 0)`, popcount via a 256-entry table,
20× oversample, exact rescore.

| n | exact cosine top-50 | Hamming + rescore | recall@50 (Hamming vs exact) | float32 bytes | bit bytes |
|---|---|---|---|---|---|
| 10,000 | 0.8 ms | 1.8 ms | 0.82 | 31 MB | 1.0 MB |
| 100,000 | 10.0 ms | 15.4 ms | **0.40** | 307 MB | 9.6 MB |
| 500,000 | 50.8 ms | 74.3 ms | 0.30 | 1,536 MB | 48 MB |

Serialization, 10,000 vectors: **JSON text 16,921 B/vector, parse
1,972 ms; packed `<f4` 3,072 B/vector, parse 1.6 ms** — 5.5× the bytes
and ~1,200× the parse time. The 2026-07-25 study estimated 3–4× from
per-float sizes; the parse cost is the larger term and it was
underestimated. Two conclusions: packed float32 is not an optimization,
it is the floor's precondition; and the Hamming prefilter's recall on
structureless vectors is bad enough that it cannot be the default
without the §10.5 measurement on real embeddings (in-memory numpy math
is already so cheap that the prefilter buys nothing until the wire is
the bottleneck).

---

## 13. Prior art consulted (cited and described; nothing copied)

### 13.1 Why not the engines' own ranking

| engine | what it offers | why it cannot be glean's lexical leg |
|---|---|---|
| PostgreSQL 17/18 core | `ts_rank`, `ts_rank_cd`, weights D/C/B/A = {0.1, 0.2, 0.4, 1.0}, length normalization bits | docs: "the ranking functions do not use any global information" — no IDF (https://www.postgresql.org/docs/17/textsearch-controls.html); the 2026-04-20 memo reached the same conclusion for the old tree |
| SQLite FTS5 | real BM25 (`bm25()`, k1 = 1.2, b = 0.75, per-column weights; negative-is-better) | its own tokenizer; SQLite-only; the tokenizer divergence already bit grep (`2026-07-16-fts5-trigram-tokenizer-divergence.md`) |
| MySQL InnoDB | `MATCH ... AGAINST`, `IDF = log10(N/n)`, `rank = TF × IDF²`, no length normalization, 3-char min token, built-in stopwords | not BM25; drops `io`, `fd`, `rx` (https://dev.mysql.com/doc/refman/8.4/en/fulltext-boolean.html) |
| SQL Server | CONTAINSTABLE/FREETEXTTABLE RANK 0–1000; FREETEXT is Okapi k1 = 1.2, b = 0.75, k3 = 8 | "The rank value doesn't hold any significance across queries" and drifts until master merge (https://learn.microsoft.com/en-us/sql/relational-databases/search/limit-search-results-with-rank) |
| Oracle Text | `CONTAINS ... SCORE`, Salton-style, truncated 0–100, collection-relative | scores change as documents are inserted; AND = min, OR = max (https://docs.oracle.com/en/database/oracle/oracle-database/19/ccref/oracle-text-scoring-algorithm.html) |

### 13.2 Lexical engines

- **Lucene** `091a987`: `BM25Similarity` k1 = 1.2, b = 0.75, non-negative
  idf, `discountOverlaps` (`BM25Similarity.java:109-140`); 1-byte length
  norms via `SmallFloat.intToByte4` (`SmallFloat.java:103-156`) with a
  256-entry saturation cache (`:215-221`); `CombinedFieldQuery` as BM25F
  (`CombinedFieldQuery.java:284-312`, weights ≥ 1); top-k pruning via
  impacts + `MaxScoreBulkScorer` / `WANDScorer`
  (`CompetitiveImpactAccumulator.java:25-39`, `MaxScoreBulkScorer.java:28-43`,
  `WANDScorer.java:32-55`), `TOTAL_HITS_THRESHOLD = 1000`
  (`IndexSearcher.java:100`); multiplicative bounded boosts
  (`FunctionScoreQuery.java:84-85, 268`).
- **tantivy** `266a6c4`: same constants and idf (`bm25.rs:8-9, 52-56`),
  keeps the `(k1+1)` factor (`:159`); 256-entry fieldnorm table
  (`fieldnorm/code.rs:13, 268-273`); block-WAND
  (`block_wand_union.rs:7-113`) over 128-doc blocks with `(fieldnorm_id,
  max_tf)` skip data (`postings/skip.rs:32-41`); default tokenizer has no
  stemming and no stopwords (`tokenizer_manager.rs:61-81`).
- **bm25s** `a213158`: eager scoring — `idf × tf-component` precomputed
  per (token, doc) into a CSC matrix, query = column-slice sums
  (`scoring.py:246-300`, `__init__.py:312-318`); k1 = 1.5 default,
  variants lucene/atire/bm25l/bm25+ (`scoring.py:115-219`); corpus-level
  idf with post-hoc masking (`__init__.py:582-612`); English stopwords on
  by default (`tokenization.py:152-155`); paper arXiv 2407.03618.
- **zoekt** `a9206004`: heuristic score bands — word match 500, partial
  50, basename 7,000, symbol 7,000, kind × 100
  (`contentprovider.go:588-609, 720-748`); file = `1e7 × score + 100 ×
  repoRank + 10 × docOrder` (`score.go:343-352`); experimental BM25 with
  *constant* idf ("idf can down-weight some keywords too much",
  `score.go:356-359`), filename/symbol matches counted as 5 occurrences
  (`:249-282`); results as `FileMatch` with `LineMatches`/`ChunkMatches`
  (`api.go:78, 156-181`).
- **codesearch** `b34f2a0`: no ranking — index order through `regexp.Grep`
  (`cmd/csearch/csearch.go:116-147`).
- **pyserini** `71072b4`: k1 = 0.9, b = 0.4 default; MS MARCO passage
  0.82/0.68, doc 4.46/0.82 (`_searcher.py:583`, `__main__.py:47-58`).

### 13.3 Fusion and hybrid frameworks

- **ranx** `7363db0`: 24 fusion methods (`fusion/__init__.py:1-33`); RRF
  k = 60, 0-based rank + 1 (`rrf.py:22, 39`); `wsum` fills missing docs
  with 0 (`wsum.py:17-25`); default normalization min-max
  (`meta/fuse.py:8-12`); `optimize_fusion` is a simplex grid search at
  step 0.1, RRF k swept 10..100 (`fusion_optimization/optimize_weights.py:11-25`,
  `optimize_rrf.py:14-20`).
- **llama_index** `d802122`: `QueryFusionRetriever` modes
  reciprocal_rerank / relative_score / dist_based_score / simple, k = 60,
  weights ignored in RRF, DBSF = mean ∓ 3σ min-max
  (`fusion_retriever.py:24-30, 113-211`); `alpha` is store-interpreted
  (Postgres store warns it is unsupported, `.../postgres/base.py:1032-1051`);
  `NodeWithScore` = node + one float (`schema.py:1035-1095`);
  `BaseEmbedding` splits query/text, `embed_batch_size` = 10
  (`base/embeddings/base.py:81-86, 133, 272`).
- **haystack** `71b0ee6`: `DocumentJoiner` concatenate / merge / RRF /
  DBSF, k = 61 with 0-based ranks, weights multiplicative on RRF terms
  (`document_joiner.py:19-27, 195-260`, `utils/misc.py:156-182`);
  `Document(content, meta, score, embedding, sparse_embedding)`
  (`dataclasses/document.py:32-54`); `TextEmbedder` vs `DocumentEmbedder`
  protocols (`embedders/types/protocol.py:10-45`).
- **lancedb** `2fbf6d6`: hybrid runs FTS and vector concurrently, min-max
  or rank normalizes, default `RRFReranker(K=60)`
  (`query.py:2211-2330, 3829-3850`, `rerankers/rrf.py:15-36`);
  `LinearCombinationReranker(weight=0.7)` vector-heavy
  (`linear_combination.py:12-38`); `EmbeddingFunction` splits
  `compute_query_embeddings` / `compute_source_embeddings`, the registry
  serializes the binding into table metadata
  (`embeddings/base.py:96-108, 169`, `registry.py:91-145`).
- **OpenSearch neural-search** `972d698`: normalization (min_max / l2 /
  z_score / rrf) and combination (arithmetic / geometric / harmonic mean,
  rrf) as orthogonal named stages; RRF constant 60 computed in
  `BigDecimal` for cross-shard determinism
  (`RRFNormalizationTechnique.java:44-45, 223-242`).
- **pyserini** fusion: rrf k = 60 on 1-based TREC ranks; `HybridSearcher`
  fills a missing side with that side's min and uses `alpha = 0.1` on
  sparse (`fusion/_base.py:30-89`, `search/hybrid/_searcher.py:40-91`).
- **Web**: Cormack et al. 2009 (k = 60 "near-optimal, not critical"; RRF
  within ~1% of CombMNZ on LETOR 3,
  http://cormack.uwaterloo.ca/cormacksigir09-rrf.pdf); Elasticsearch RRF
  retriever (`rank_constant` 60, https://www.elastic.co/guide/en/elasticsearch/reference/current/rrf.html)
  and linear retriever (https://www.elastic.co/docs/reference/elasticsearch/rest-apis/retrievers/linear-retriever);
  Weaviate `relativeScoreFusion` default since 1.24, alpha 0.75
  (https://weaviate.io/blog/hybrid-search-fusion-algorithms); Bruch, Gai
  & Ingber, TOIS 2023 (https://arxiv.org/abs/2210.11934); Anthropic
  contextual retrieval (5.7% → 3.7% → 2.9% → 1.9%,
  https://www.anthropic.com/news/contextual-retrieval); turbopuffer
  client-side fusion with optional server RRF
  (https://turbopuffer.com/docs/hybrid); Vespa rank-profile fusion
  (https://docs.vespa.ai/en/learn/tutorials/hybrid-search.html).

### 13.4 Vectors, graphs, embeddings

- **pgvector** `e48241b`: HNSW `m = 16, ef_construction = 64`,
  `hnsw.ef_search` 40, filtering applied *after* the index scan,
  `hnsw.iterative_scan` (0.8.0) with `max_scan_tuples`, `binary_quantize`
  + `<~>` + rerank, 2,000-dim index cap (`README.md:252, 265-284,
  424-538, 594-607, 935`).
- **sqlite-vec** `04d28bd`: `vec0` virtual table, KNN via `MATCH`,
  partition-key and metadata columns for filtered KNN (`README.md:18,
  79-84`); a loadable extension — not assumable at the floor.
- **HippoRAG** `2f52a86`: igraph PPR over entity + passage nodes, dense
  scores min-max normalized and seeded at `passage_node_weight = 0.05`,
  damping 0.5, `linking_top_k = 5`, `retrieval_top_k = 200`
  (`HippoRAG.py:2040-2110, 2164-2193`, `utils/config_utils.py:91-195`).
- **graphify** `43d54ac` (v8): tree-sitter extraction → NetworkX graph →
  Leiden (graspologic) or Louvain communities → god nodes / surprising
  connections → GRAPH_REPORT.md and exports (`ARCHITECTURE.md` pipeline
  table, `cluster.py:1-76`, `analyze.py`); a community/centrality *report*
  for an LLM, not a query-time ranker — consistent with treating graph
  analytics as index-time data.
- **model2vec** `280b341`: static embeddings, 50× smaller, up to 500×
  faster on CPU, ~30 MB best model, potion-base-8M from bge-base-en-v1.5
  (`README.md:44, 136-138, 166`). **fastembed** `c48247f`: `embed(batch_size=256)`,
  separate `query_embed` / `passage_embed` (`text_embedding.py:157-194`).
- **Web**: Sourcegraph PageRank ranking
  (https://about.sourcegraph.com/blog/new-search-ranking) and BM25F
  (https://sourcegraph.com/blog/keeping-it-boring-and-relevant-with-bm25f);
  OpenAI Matryoshka numbers
  (https://openai.com/index/new-embedding-models-and-api-updates/);
  EmbeddingGemma-300M 768-d (https://huggingface.co/google/embeddinggemma-300m),
  Qwen3-Embedding-0.6B 32–1024-d, nomic v2 MoE 768→256 with
  `search_query:`/`search_document:` prefixes
  (https://huggingface.co/nomic-ai/nomic-embed-text-v1.5); SQL Server
  2025 vectors (https://learn.microsoft.com/en-us/sql/sql-server/ai/vectors?view=sql-server-ver17);
  MySQL 9.7 vector functions
  (https://dev.mysql.com/doc/refman/9.7/en/vector-functions.html);
  Oracle approximate search with `TARGET ACCURACY`
  (https://blogs.oracle.com/database/using-hnsw-vector-indexes-in-ai-vector-search).

---

## 14. Clarifications this memo cannot settle

- [NEEDS CLARIFICATION: CJK tokenization — codepoint bigrams in the
  lexical tokenizer, or vector-only for CJK bodies? (§2.2)]
- [NEEDS CLARIFICATION: is one embedding space per mount the v1
  contract, with the `spaces` registry reserved for later — or must v1
  already fan out across spaces per the 2026-07-25 memo's Q8? The schema
  here supports both; the query path in §4.3 assumes one.]
- [NEEDS CLARIFICATION: the `Embedder` is injected on `DatabaseStorage`.
  Should the router also accept one and push it to every mount lacking
  its own, so a single model serves a whole namespace by default?]
- [NEEDS CLARIFICATION: `vfs.glean.stale` is an info record. Should an
  agent-facing MCP host surface it, or is the count purely for
  operators?]
