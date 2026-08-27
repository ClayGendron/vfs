# glean in the engine: the per-dialect matrix, the lexical index, and the fused statement

- **Status**: research memo — design input for the glean *storage* ADR
  (the fused statement, the lexical index tables, the vector tiers, the
  dialect facts, and the freshness posture). One of five memos from the
  2026-08-26 glean research leg (brief:
  [2026-08-26-glean-brief.md](2026-08-26-glean-brief.md)). Companions:
  [fusion and cross-mount merge](2026-08-26-glean-fusion-and-cross-mount-merge.md)
  (which fusion function the statement compiles),
  [ranking signals and the ranker API](2026-08-26-glean-ranking-signals-and-ranker-api.md)
  (the `signals` join), [the embedding seam](2026-08-26-glean-embedding-seam.md)
  (who fills the vector column and how it is stored),
  [previews and the result shape](2026-08-26-glean-previews-and-result-shape.md).
  The landscape study
  ([studies/2026-08-26-glean/landscape.md](studies/2026-08-26-glean/landscape.md))
  is the standalone awareness record for graphify, gbrain, the graph-RAG
  and agent-memory systems, the code-search products and the hybrid-SQL
  vendors; it decides nothing and is not re-summarised here beyond its
  positioning line. Commits us to nothing.
- **Date**: 2026-08-26
- **Owner**: Clay Gendron
- **Question**: Across Postgres (+pgvector), MariaDB 11.8, MySQL 9
  community, SQL Server 2025, Oracle 26ai and SQLite (+FTS5, +sqlite-vec):
  can one SQL statement per mount carry a vector top-k leg, a BM25 top-k
  leg, the fusion, the glob scope inside each leg, per-entry aggregation
  and `LIMIT n`? Is the lexical leg each engine's own full-text ranking
  or a portable index of our own? What does the honest floor cost where
  no server-side distance exists? And what does glean serve between a
  write and the next reindex?
- **Evidence gathered**: the engine-matrix study
  ([studies/2026-08-26-glean/engine-matrix.md](studies/2026-08-26-glean/engine-matrix.md))
  — every engine claim executed on a running container this session
  (pgvector/pgvector:pg17 with pgvector 0.8.6, mariadb:11.8.9, mysql:9.7.2,
  SQL Server 2025 RTM-CU8 with `mssql-server-fts` installed
  in-container, Oracle 26ai Free 23.26.2 regular image, SQLite 3.50.4 +
  sqlite-vec 0.1.9) with scripts and raw JSON beside it; the lexical-leg
  study ([lexical-leg.md](studies/2026-08-26-glean/lexical-leg.md)) —
  BM25 variants, engine FTS scoring formulas, tokenisation prior art,
  and an executed build of the portable term tables from a real corpus
  split by `Chunk.split_batch` (the vfs repo, 4,909 chunks; a linux
  `drivers/gpu` slice at 2,690 and 11,608 chunks — the ~50k build did
  not complete on this machine and was not retried), plus an EXPLAIN
  diagnosis of the scope-join shapes; the independent design's
  SQL-vs-Python measurement
  ([unconstrained-design.md §12](studies/2026-08-26-glean/unconstrained-design.md));
  the landscape study's vendor record (§7).
- **Headline**: **The hand-written fused statement runs as one statement
  and returns byte-identical top-5 rankings on five engines** —
  Postgres, MariaDB, SQL Server, Oracle, SQLite — with only the three
  leg expressions and the row-limit spelling varying per dialect;
  SQLAlchemy Core compiles the skeleton. MySQL community is the
  permanent floor: it has the `VECTOR` type but no `DISTANCE()`,
  refuses any index on the column, and pymysql cannot decode the wire
  type — its vector leg is a client-side exact scan. **Scope predicates
  defeat ANN** on MariaDB and Oracle (exact scans, verified in plans),
  post-filter on SQL Server, and are planner-arbitrated on pgvector; so
  scope-first exact is the correct default and ANN is an unscoped
  accelerator. SQL Server's DiskANN makes the table read-only;
  Oracle's `DBMS_HYBRID_VECTOR` cannot use our embeddings. **The
  lexical leg is ours, not the engine's**: native FTS is true BM25 only
  on SQL Server `FREETEXTTABLE` and FTS5, and every engine owns its own
  tokenizer, so a portable `lex_terms(epoch, term, chunk_id, tf, weight)`
  table scored by `SUM(weight) … GROUP BY chunk_id` — a published,
  reproduced method — gives the same ranking on all six engines
  (top-10 overlap 1.0 and Kendall τ 1.0 against bm25s), at 1–3 ms for
  3–6-term queries over 11.6k chunks, 2–3× cheaper than evaluating the
  formula at query time, at ~2.1–2.8× the content bytes. **Packed
  float32 vectors are the floor's precondition** (14× faster, 5×
  smaller than JSON at 50k). Freshness: the lexical index rides the gram
  epoch's `encoded` partition, and a budgeted live-text overlay scores
  the `NOT encoded` set at ~1.8 ms per dirty entry so the file an agent
  just wrote is searchable before the next reindex.

---

## 1. One statement, five engines, identical rankings

The brief's shape — two ranked CTEs, fusion, scope inside each leg,
per-entry max, `LIMIT n` — ran as one statement and returned the same
top-5 with the same scores on Postgres 17.11 + pgvector 0.8.6, MariaDB
11.8.9, SQL Server 2025 CU8, Oracle 26ai Free 23.26.2 and SQLite 3.50.4
+ FTS5 + sqlite-vec (100 entries × 4 chunks, 8-dim synthetic vectors,
a lexical target planted in ten entries, a ten-entry scope, k = 60,
per-leg k = 20, n = 5). MySQL 9.7.2 ran the lexical leg only. The
portable skeleton replaces the `FULL OUTER JOIN` of the MariaDB and
Azure SQL reference queries with `UNION ALL` + `GROUP BY` + `SUM` —
exactly RRF (a chunk absent from a leg contributes 0), and the only form
that needs nothing beyond CTEs, window functions, `UNION ALL`, `GROUP
BY` and a row limit, all present on all six engines (MariaDB and MySQL
have no `FULL OUTER JOIN`; SQLite gained it at 3.39):

```sql
WITH vec_top AS (SELECT c.id, c.entry_id, <DIST(c.embedding, :q)> AS dist
                 FROM chunks c JOIN <SCOPE> s ON s.id = c.entry_id
                 WHERE c.embedding IS NOT NULL ORDER BY dist <LIMIT :kv>),
     vec     AS (SELECT id, entry_id, ROW_NUMBER() OVER (ORDER BY dist) AS rnk FROM vec_top),
     lex_top AS (... <SCORE> ... ORDER BY score DESC <LIMIT :kl>),
     lex     AS (SELECT id, entry_id, ROW_NUMBER() OVER (ORDER BY score DESC) AS rnk FROM lex_top),
     legs    AS (SELECT id, entry_id, 1.0/(:k + rnk) AS s FROM vec
                 UNION ALL SELECT id, entry_id, 1.0/(:k + rnk) AS s FROM lex),
     per_chunk AS (SELECT id, entry_id, SUM(s) AS s FROM legs GROUP BY id, entry_id)
SELECT entry_id, MAX(s) AS score FROM per_chunk GROUP BY entry_id
ORDER BY score DESC, entry_id <LIMIT :n>
```

Two shape facts the builder must keep: ranking happens in a CTE *above*
the `LIMIT`ed leg — a window inside the leg forces the planner to sort
everything before limiting and defeats an ANN index scan (verified on
pgvector); and Core compiles the limit per dialect (`TOP n`, `FETCH
FIRST n ROWS ONLY`, `LIMIT n`). The fusion memo amends the arithmetic
(convex combination of normalised scores as the reference, RRF as the
rank-only floor) and moves the `MAX … GROUP BY entry_id` *into* each
leg so entries, not chunks, are ranked and limited; both are the same
skeleton with different CTE contents. The `signals` join (signals memo)
is one `LEFT JOIN` on `entry_id` per configured signal.

The leg expressions per dialect (all verified):

| dialect | vector distance | lexical predicate / score | row limit |
|---|---|---|---|
| Postgres | `c.embedding <=> CAST(:q AS vector)` | our tables (§3); native `@@` / `ts_rank_cd` exists but is not BM25 | `LIMIT` |
| MariaDB 11.8 | `VEC_DISTANCE_COSINE(c.embedding, VEC_FromText(:q))` | our tables; InnoDB `MATCH … AGAINST` exists, not BM25 | `LIMIT` |
| MySQL 9 | **none** — leg is client-side | our tables | `LIMIT` |
| SQL Server 2025 | `VECTOR_DISTANCE('cosine', c.embedding, CAST(:q AS VECTOR(n)))` | our tables; `FREETEXTTABLE` is BM25 but refused in `master` and asynchronously populated | `TOP (:n)` |
| Oracle 26ai | `VECTOR_DISTANCE(c.embedding, TO_VECTOR(:q), COSINE)` | our tables; `CONTAINS`/`SCORE` is Salton, not BM25 | `FETCH FIRST :n ROWS ONLY` |
| SQLite | `vec_distance_cosine(blob, :q)` scalar over a BLOB column, or vec0 `MATCH … AND k = :kv AND rowid IN (scope)` | our tables; FTS5 `bm25()` is BM25 (negated) | `LIMIT` |

Scope works inside every leg as an `IN`-list on `entries.id` (two
expanding binds per statement, so the per-leg list is at most
`(budget − fixed binds)/2` under `membership_budget`) or as a join to a
scope CTE; on SQLite it pushes into the vec0 KNN and the FTS5 MATCH via
`rowid IN (subquery)`. Two engine facts that bite tests: InnoDB
full-text indexes are visible only after commit (0.0 for every row
inside the writing transaction), and SQL Server full-text is refused in
`master`/`tempdb` — the conformance harness's `master` URL cannot host a
native lexical leg, one more reason the leg is ours.

## 2. Per-dialect ground truth (2026-08-26, verified)

| | Postgres 17 + pgvector 0.8.6 | MariaDB 11.8.9 | MySQL 9.7.2 community | SQL Server 2025 CU8 | Oracle 26ai Free | SQLite 3.50 + sqlite-vec 0.1.9 |
|---|---|---|---|---|---|---|
| vector type / storage cap | `vector` ≤ 16,000, `halfvec` | `VECTOR(n)` — InnoDB's 65,535-byte row cap binds before 16,383 | `VECTOR(n)` ≤ 16,383 | `VECTOR(n)` ≤ 1,998 | `VECTOR(n, fmt)` ≤ 65,535 | vec0 or BLOB |
| server-side distance | `<=>` `<->` `<#>` `<+>` | `VEC_DISTANCE_COSINE/EUCLIDEAN` (no dot) | **none** | `VECTOR_DISTANCE` GA | `VECTOR_DISTANCE` | `vec_distance_*`, vec0 KNN |
| ANN index | HNSW/IVFFlat ≤ 2,000 dims (`halfvec` ≤ 4,000) | MHNSW `VECTOR INDEX`, column `NOT NULL` | **none** — "vector column cannot be used as key" | DiskANN **preview**, needs a user DB and `PREVIEW_FEATURES`, **table becomes read-only** (error 42231), `VECTOR_SEARCH` needs a `DECLARE`d variable | HNSW/IVF, needs `vector_memory_size` set at the CDB root (Free image ships 0) | none (brute force) |
| ANN + scope predicate | planner arbitrates: HNSW + filter for a 10-entry scope, exact bitmap + heapsort for a half-corpus scope (50k rows) | index **not used** when scoped → exact `range` + filesort | n/a | `VECTOR_SEARCH` **post-filters** (1 of 5 rows survived) | HNSW/IVF **not used** when scoped → `TABLE ACCESS FULL`; `FETCH APPROX` without an index silently runs exact | vec0 honours `rowid IN` prefilter |
| native FTS is BM25? | no — `ts_rank_cd` cover density, "no global information" | no — TF·IDF², no length norm, 3-char min token | no | `FREETEXTTABLE` yes (Okapi 1.2/0.75, expansions baked in); `CONTAINSTABLE` no | no — Salton, 0–100, "inserting … is likely to change the score" | yes (`bm25()`, negated) |
| driver notes | pgvector-python types | `VEC_FromText`/`VEC_ToText` | pymysql **cannot decode the raw `VECTOR` wire type**; `HEX`/`TO_BASE64` work | pyodbc sees vectors as JSON text (8 + 4n bytes) | in-tree SQLAlchemy `VECTOR`, `array.array` binds | extension loaded on `connect` |
| vector-leg tier | native ANN or exact | ANN unscoped / exact scoped | **client floor** | exact (ANN unshippable) | ANN unscoped / exact scoped | exact in C |

Cross-cutting: IDF-type statistics are corpus-global on every engine;
scoping by join changes which rows are ranked, never the term weights.
`DBMS_HYBRID_VECTOR` is a real Oracle primitive (RSF/RRF/WRRF, document
vs chunk mode, `MAX` aggregator) but a hybrid vector index embeds a
*text* column with an in-database ONNX model — `DRG-51504: need to
specify model name`, `ORA-02327` on a `VECTOR` column — so it is the
wrong seam for a Storage-owned provider.

## 3. The lexical leg is ours

### 3.1 Why not engine FTS

Five incompatible scores (§2), five engine-owned tokenizers (MySQL's
3-char minimum drops `os`, `fd`, `id`; FTS5's `unicode61` splits on `_`
unless configured; Postgres's parser has its own view of `foo_bar`), one
asynchronously populated (SQL Server), one whose scores drift with
inserts (Oracle). Under rank-only fusion the score scale would not
matter — but the *rankings* differ in quality (unsaturated TF·IDF on
MySQL vs BM25 on SQLite), which makes the cross-mount merge dishonest
in a way no normalisation fixes, and the conformance suite cannot pin a
stable top-*n* across engines that disagree on order. The engine-matrix
study left engine FTS as a "defensible tier" (its fork F1); the lexical
study, the independent design ("no engine FTS anywhere … one scorer,
one ranking on every engine") and the landscape record (takeaway 2:
"the lexical leg must carry document frequency, so it is ours") close
it. Not built.

### 3.2 The portable tables, and why the variant does not matter

Kamphuis, de Vries, Boytsov & Lin (ECIR 2020) compared eight BM25
variants on three collections and found no significant difference
between any pair — and ran the study *in a relational database*, each
variant as one SQL query over term/document tables, verified against
Anserini. BM25-in-SQL is a published, reproduced method. bm25s's shape
is the table's shape: it precomputes `idf · tfc(tf, dl)` per `(token,
doc)` into a sparse matrix and answers a query as a column-slice sum;
`lex_terms(term, chunk_id, weight)` with `SUM(weight) … GROUP BY
chunk_id` is that matrix as rows. Legal because idf and avgdl are
constants of one build — for us, of one epoch.

```
lex_docs (epoch, chunk_id, entry_id, dl)          PK (epoch, chunk_id); index (epoch, entry_id)
lex_terms(epoch, term, chunk_id, tf, weight)      PK (epoch, term, chunk_id)   -- weight = idf·tfc, precomputed
lex_df   (epoch, term, df, idf)                   PK (epoch, term)             -- also answers the router's (df, N, avgdl) export
lex_stats(epoch, n_docs, avg_dl)                  PK (epoch)
```

The PK order makes each term's rows a contiguous B-tree run — a posting
list stored as rows. Formula: Lucene-accurate (non-negative IDF, exact
lengths, `(k1+1)` kept so single-term scores read as `≤ (k1+1)·idf`),
k1 = 1.2, b = 0.75 (Lucene, tantivy, FTS5, zoekt; pyserini's 0.9/0.4 is
a newswire tuning), both in the epoch's `options_hash`. Fidelity is
exact: top-10 overlap 1.0 and Kendall τ 1.0 against bm25s on 45 queries;
the score ratio is exactly 2.2 = k1+1.

### 3.3 The tokenizer

One tokenizer beside `code_grams.py`, sharing `fold_content` (Turkic-i
pre-fold + `casefold`) so the query, the index, the gram stream and the
preview's bolding agree: split on runs of `[^\p{L}\p{N}_]`, then on `_`
and case change, **emitting the whole folded identifier and its parts**
(Lucene's `WordDelimiterGraphFilter` with `PRESERVE_ORIGINAL`:
`PostingsBuilder → postingsbuilder, postings, builder`), drop
single-character parts, keep digit-led tokens whole, cap term length at
64 bytes. **No stemming, no stop list**: identifiers are not inflected,
stemming would merge `indexing` with `index`, and IDF does the stop-word
job continuously (Kamphuis: the stop list is the *larger* source of
variance). The one latency knob is a **df ceiling** on query terms
(Lucene's `CommonTermsQuery`), with a warning record naming dropped
terms. Sourcegraph/zoekt's substring-induced tokenisation and
constant-IDF BM25F, GitHub's sparse grams, and tantivy's plain
`SimpleTokenizer` (which loses the whole identifier) were the
alternatives. Pure-Python reference first; the Rust engine port behind
`vfs.native` when the build's tokenizer share (~40 % today) is measured
to matter, on the gram builder's precedent. BM25F fields (path segments,
symbols) are a later fork: a boosted-tf column at build time, no
statement change. CJK bodies yield one token per run and are a named
open question (codepoint bigrams vs vector-only).

### 3.4 Measured

Build cost and size (`Chunk.split_batch` chunks, pure-Python tokenizer,
SQLite):

| corpus | files | content MB | chunks | term rows | rows/chunk | vocab | build s / 1k files | `lex_terms` MB (int term-id) | total MB | × content |
|---|---|---|---|---|---|---|---|---|---|---|
| vfs repo | 628 | 7.5 | 4,909 | 691,845 | 141 | 29,690 | 4.3 | — | 20.9 | 2.8 |
| linux/gpu | 256 | 4.5 | 2,690 | 286,087 | 106 | 29,880 | 3.9 | 9.0 (7.0) | 10.2 | 2.2 |
| linux/gpu | 1,024 | 19.6 | 11,608 | 1,166,497 | 100 | 87,862 | 3.9 | 37.8 (29.5) | 41.9 | 2.1 |

Statement latency, median ms over 15 queries per arity (3-term = two
mid-df + one term in > 20 % of chunks; 6-term = one rare + four mid +
one common):

| chunks | arity | precomputed `SUM(weight)` | runtime formula (3 joins) | + entry MaxP | scope: 5 % id list | scope: 50 % id list | scope: segment join |
|---|---|---|---|---|---|---|---|
| 4,909 | 1 / 3 / 6 | 0.018 / 0.371 / 0.416 | 0.039 / 0.979 / 1.234 | 0.196 / 0.969 / 1.040 | 0.105 / 0.294 / 0.482 | 0.989 / 2.841 / 5.094 | 0.031 / 0.625 / 0.700 |
| 2,690 | 1 / 3 / 6 | 0.016 / 0.272 / 0.206 | 0.035 / 0.772 / 0.556 | 0.119 / 0.704 / 0.526 | 0.049 / 0.122 / 0.192 | 0.422 / 1.375 / 2.387 | 0.029 / 0.607 / 0.445 |
| 11,608 | 1 / 3 / 6 | 0.023 / 1.016 / 0.896 | 0.051 / 3.134 / 2.690 | 0.416 / 2.693 / 2.380 | 0.208 / 0.638 / 1.142 | 1.808 / 5.867 / 10.775 | 0.050 / 2.492 / 2.223 |

Readings: precomputed weights are 2–3× faster than the runtime formula
and need one table in the statement, not four; cost tracks the query's
*df sum*, not corpus size (a mid-df single term is tens of microseconds
at every size; the common term dominates the 3-term rows) — the df
ceiling is the knob that matters; MaxP is cheap (0.1–0.7 ms); a wide id
allow-list *slows* the statement (probed per scored row, prunes
nothing), and the **segment join is cheap at every width** (an indexed
equality on `(segment, entry_id)` the planner can only run one way).
The id allow-list is planner-fragile *as a JOIN*: the "scope-driven"
spelling measured 680–695 ms for 3–6-term queries at 11.6k chunks —
EXPLAIN shows SQLite, without statistics, walking the ~1,000 scoped
chunks and re-running the term filter per chunk; after `ANALYZE` the
same SQL replans term-driven at 38 ms, still 60× the unscoped cost.
Two spellings are fast and planner-stable at every width measured: the
**semi-join** `t.chunk_id IN (SELECT chunk_id FROM lex_docs WHERE
entry_id IN (...))` — 0.35 / 0.32 ms (3- / 6-term) at a 5 % scope, 0.21
/ 0.20 ms at 0.5 % — and the **scope-driven PK probe** (`lex_docs`
cross-joined to `lex_terms` on `term IN (...) AND chunk_id =
sd.chunk_id`), 0.75 / 1.37 ms at 5 % and 0.07 / 0.13 ms at 0.5 %, which
probes the `(epoch, term, chunk_id)` primary key per (chunk, term) and
**needs no secondary index**. Incremental maintenance (delete +
reinsert one entry's rows) needs a chunk-keyed index (+69 % bytes) and
cost 97 s for 1,000 entries at 11.6k chunks (6.7 s at 2,690) vs ~4 s to
rebuild the whole 1,024-file corpus: the index is a regenerable epoch
cache, rebuilt whole like the postings. The
independent design measured the same shape on a 29,711-chunk C corpus:
SQL-side scoring 1.3–9.5 ms vs 2.8–21 ms fetching postings into Python,
with the SQL path shipping 50 rows where the Python path shipped 25,848.

## 4. The vector leg: tiers, floor, and bytes

Three tiers producing the same `(chunk_id, distance)` top-k list,
selected per dialect and per query, never per caller:

1. **Native** where a distance function exists (Postgres, MariaDB, SQL
   Server, Oracle, SQLite): `ORDER BY <DIST> LIMIT k` with the scope
   predicate in the same statement. ANN applies only when the planner
   will use it — unscoped queries on MariaDB and Oracle, Postgres with
   `hnsw.iterative_scan = relaxed_order` where the extension is 0.8+ —
   and the tier served is a plan-level fact on Postgres/Oracle and a
   configuration fact (index present, no scope) on MariaDB/SQL Server.
   DiskANN on SQL Server 2025 on-prem is not shipped (read-only table).
2. **Client floor** (MySQL community, `GENERIC`): `SELECT id, entry_id,
   <packed vector> FROM chunks WHERE <scope>`, scored in numpy in
   membership-budget batches with a running top-k, fused in Python. The
   fuser is the same function the cross-mount merge needs, so the floor
   costs no second algorithm.
3. The July floor's upgrades (sign-bit prefilter, plain-SQL IVF) stay
   unbuilt: the independent design measured Hamming recall@50 of 0.40 at
   100k on structureless vectors — a warning, not a verdict, to be
   re-run on real embeddings before any gated tier exists.

The floor benchmark (MySQL 9.7.2, 384-d, best of 3, top-10 cosine in
numpy):

| N | JSON text (7,975 B/vector) | packed float32 (1,536 B) |
|---|---|---|
| 10,000 | 0.907 s (90 % `json.loads`) | **0.068 s** |
| 50,000 | 4.692 s | **0.332 s** |

Honest interactive ceiling on the vector leg alone (≈ 1 s): ~10k scoped
chunk vectors as JSON, **~150k packed**, at 384 dims — divide by four
for 1,536. Linear degradation, recall 1.0, never a declared cap. Packed
little-endian float32 in a `LargeBinary` is therefore the portable
column (the embedding memo carries the storage decision and the
independent design's ~1,200× parse-time confirmation), with native types
where modelled — pgvector via pgvector-python, Oracle's in-tree `VECTOR`,
and two small `UserDefinedType`s for SQL Server (`VECTOR(n)` as JSON over
pyodbc) and MariaDB (`VEC_FromText`/`VEC_ToText`) — and never MySQL's.

## 5. Scope pushdown: predicate, not list

RRF and convex fusion both need each leg's global rank over the whole
scope, so a top-k taken per id-chunk is not the top-k of the union — a
scope wider than one membership chunk breaks single-statement fusion.
Two lawful shapes: (a) express the scope as a **predicate** — the
segments join / path-prefix range that grep's `_pushdown_terms` already
uses (ADR 040) — so one statement covers any scope width with zero id
binds (measured cheap at every width in §3.4; the Postgres `path LIKE
'src/mod3/%'` join plan is exact); (b) an id allow-list spelled as a
**semi-join subquery** (never a JOIN — §3.4), chunked under
`membership_budget`, with per-chunk leg top-k merged client-side and
fused in Python when it exceeds one chunk, and the PK-probe spelling as
the narrow-scope rung chosen by a width threshold like grep's
`_ladder_defers`. (a) is the design; (b) is the fallback for
observation-piped scopes (brief gap 14), which are lists by nature.
Both (b) spellings were measured on SQLite only; the engine legs must
run them before either is pinned, since each planner decides. The
lexical index is the first vfs index where the scope never leaves the
engine — grep's allow-list returns to the client only to intersect with
decoded posting blobs, and here there are no blobs.

## 6. Freshness: what glean serves between a write and the next reindex

A content write stamps `chunked=False, encoded=False, indexable=False`
and touches no chunk row; the old chunks stay until `chunk_dirty`
re-splits them (new ids). Any chunk-keyed lexical epoch therefore scores
the *previous* body. grep's answer to the same shape is the flag
partition: `encoded=True` implies the grams are in the current epoch;
everything `NOT encoded` is the scan overlay. Recommended posture — the
same partition, budgeted:

1. The lexical epoch is built in `build_epoch`'s existing content scan
   and published by the same `encoded` flips and pointer CAS, so the
   invariant extends verbatim: **`encoded=True` implies the entry's
   terms are in the current lexical epoch.** The leg joins
   `entry.encoded`, `deleted_at IS NULL` and `user_id` scoping; a
   written-but-unreindexed entry is excluded from the index side, never
   served stale.
2. **A live-text overlay scores the `NOT encoded` set** — grep's
   `_entries_for_scan` partition — tokenised and scored client-side with
   the epoch's `idf`/`avg_dl` (one `lex_df` probe on the query's terms),
   on the same scale as the index's, merged into the lexical leg before
   fusion; bounded like grep's scan tier by the same candidate budget
   and deadline. Measured: 100 dirty entries 0.18–0.20 s, 1,000 entries
   0.9–1.8 s (~1.8 ms per entry, ~0.17 ms per chunk, pure Python).
3. **One warning record** names scanned / unconsulted / lexical-only
   counts. The same entries have `embedding IS NULL`, so they reach the
   fused list through the lexical leg alone — "K entries ranked by
   lexical match only (not yet embedded)".

Rejected: serving stale chunk terms silently (violates the invariant
grep pays for); excluding the dirty set with no overlay (blind to the
file the agent just wrote — mem0's "searchable on the next turn"
argument, recorded in the 2026-08-25 chunking memo; the independent
design chose this and named it a top-three risk); a write-time term
buffer (`lex_pending`) — a legitimate *future* fork since tokenising is
cheap where splitting is not, but it puts a tokenizer on the ETL write
path the overlay makes unnecessary today.

## 7. What SQLAlchemy models, and what vfs must add

In-tree (2.1 @ 0770f6e96, compile checks on 2.0.46): pgvector types
and comparators via pgvector-python; Oracle `VECTOR`, distance
comparators, `VectorIndexConfig` DDL and `fetch(k,
oracle_fetch_approximate=True)`; the fusion skeleton (`.cte()`,
`row_number().over()`, `union_all`, `.group_by`, `.limit()`) on every
dialect. Nothing for SQL Server or MySQL/MariaDB vector types; `match()`
is only the predicate on four of six dialects. vfs adds: two
`UserDefinedType`s (SQL Server, MariaDB) selected from
`VectorType.load_dialect_impl` on the `postgres_native` pattern; a
distance-expression factory keyed by dialect (operator comparator vs
`func.*` with engine-specific argument order, and *no expression* for
MySQL/`GENERIC`); the sqlite-vec extension load on `connect` behind a
`sqlite_native`-style opt-in; and — because the lexical leg is ours —
none of the per-engine FTS DDL (no generated `tsvector` columns, GIN,
full-text catalogs, CONTEXT indexes or FTS5 virtual tables).

## 8. Declared dialect facts

Where vector configuration lives, per the profile doctrine (declare only
what SQLAlchemy takes no position on): `vector_distance ∈ {none, exact,
ann}` (sqlite `exact` via sqlite-vec only when loaded, mysql `none`,
mssql `exact`, mariadb/oracle/postgresql `ann` — Postgres only after a
first-touch probe finds the extension), `vector_dimension_cap` (pgvector
2,000 for HNSW / 16,000 storage, `halfvec` 4,000; SQL Server 1,998;
MySQL 16,383; MariaDB below 16,383 by row size; Oracle 65,535), and
`ann_honours_scope` (Postgres planner-arbitrated; MariaDB/Oracle no;
SQL Server post-filter). A space over the cap is stored but refused for
the native tier with a classified first-touch error.

## 9. The Docker legs

`postgres:17` → `pgvector/pgvector:pg17` (the plain image cannot
`CREATE EXTENSION vector`; the pgvector image is a superset);
`mariadb:11.4` → `11.8`; `mysql:8.4` → `9` (8.4 has no `VECTOR` type);
`mssql/server:2022-latest` → `2025-latest` plus a small Dockerfile
installing `mssql-server-fts` and a user database (previews and any
native-FTS probe are refused in `master`); `gvenzl/oracle-free:23-slim`
→ `:23` (regular) whenever Oracle Text matters, with
`vector_memory_size` set at the CDB root for HNSW tests — all `23` tags
now resolve to 26ai 23.26.x.

## 10. Positioning, in one line

Nothing in the field does this: the graph-RAG systems have no engine-
side lexical leg, the agent-memory systems and gbrain fuse outside the
database with hand-calibrated boosts, the code-search products with
principled ranking are purpose-built inverted indexes, and the SQL
vendors ship one copy-paste RRF recipe with true BM25 on half the
engines and a real primitive on one. The fusion statement executed by
the engine that owns the rows, scope and trash/permission predicates
inside each leg, portable across six dialects, is unoccupied
(landscape study, *Bearing on vfs*).

## 11. Recommendation for the ADR

1. **One fused statement built with Core**, the leg expressions and the
   row limit the only dialect variation, on Postgres, MariaDB, SQL
   Server, Oracle and SQLite; the same fuser in Python for MySQL,
   `GENERIC`, list-scoped calls and the cross-mount merge; a stable
   total order (`score DESC, entry_id`) as the conformance pin.
2. **The lexical leg on our own epoch-scoped tables** (`lex_docs`,
   `lex_terms`, `lex_df`, `lex_stats`), Lucene-accurate BM25 with
   precomputed weights, k1 = 1.2 / b = 0.75 in the `options_hash`, built
   in `build_epoch`'s content scan, published by the existing flips and
   CAS, reclaimed with the epochs; no engine FTS.
3. **One code-aware tokenizer** sharing `fold_content`: whole identifier
   plus parts, no stemming, no stop list, a df ceiling with a warning
   record; pure reference now, Rust behind `vfs.native` when measured.
4. **Vector tiers**: native where a distance function exists, ANN only
   where the planner will use it (unscoped, or Postgres with iterative
   scan), client floor on MySQL/`GENERIC`; packed float32 as the
   portable column; every answer records the tier that served each leg.
5. **Scope as a predicate** (segments join) inside every leg; id lists
   only for piped observations, chunked with client-side merge.
6. **Freshness**: the lexical index rides the `encoded` partition; a
   budgeted live-text overlay covers the `NOT encoded` set; one warning
   record names scanned / unconsulted / lexical-only counts.
7. **Declared dialect facts** for distance availability, dimension caps
   and ANN-with-scope behaviour; **compose bumps** per §9.

## 12. Forks the ADR must close

- **E1** — fusion in SQL on the five capable engines (recommended: one
  fewer round trip, ≤ kv + kl rows; identical rankings verified) vs
  always in Python (one code path; the fuser exists anyway). The
  `Fusion.to_sql` / `Fusion.fuse` pair in the ranker API is the
  reconciliation.
- **E2** — term text vs integer term id on posting rows: −22 % bytes vs
  one extra lookup and a second table per statement. Lean: text now.
- **E3** — precomputed weight vs `tf` + runtime formula: 2–3× latency
  and statement simplicity vs REAL bytes and k1/b frozen per epoch.
  Lean: precomputed.
- **E4** — epoch rebuild vs incremental maintenance: rebuild,
  decisively (97 s per 1,000 entries incremental at 11.6k chunks vs ~4 s
  to rebuild the corpus, +69 % bytes for its index); if a cadence ever
  binds, a set-based delete-by-chunk-range, never row-wise; a write-time
  `lex_pending` buffer is the sub-fork if a deployment's overlay budget
  proves too small.
- **E4b** — id-scope spelling: semi-join subquery (recommended) vs the
  PK probe as the narrow rung vs both behind a width threshold; to be
  confirmed on the Docker legs.
- **E5** — native vector types on SQL Server and MariaDB vs
  `VARBINARY` everywhere but Postgres/Oracle: native buys server-side
  distance on both at the cost of two custom types and MariaDB's row-
  size cap.
- **E6** — how the recall/tier record is determined: read the plan
  (`EXPLAIN` costs a round trip) vs infer from configuration (index
  present + no scope).
- **E7** — CJK tokenisation: codepoint bigrams in the lexical tokenizer
  vs vector-only for CJK bodies.
- **E8** — BM25F fields (path segments now; symbols when an extractor
  exists) as boosted-tf columns at build time — and whether the path
  field alone satisfies the landscape's "identity beats ranking"
  finding or a hard identity tier is also wanted (signals memo F8).

## Sources

Studies (this repo): `studies/2026-08-26-glean/engine-matrix.md`
(`engine-matrix/probe_*.py`, `bench_floor_mysql.py`, `results_*.json`);
`lexical-leg.md` (`lexical-leg/build_and_time.py`, `compare_bm25s.py`,
`summarize.py`, `results/report-*.json`); `unconstrained-design.md`
§4.2, §12; `landscape.md` §7 and *Bearing on vfs*; prior:
`studies/2026-07-25-multimodal-storage/vector-portability.md`,
`2026-08-17-search-storage-organizations.md`,
`2026-08-25-semantic-chunking-write-vs-reindex.md`.

Checkouts (refreshed 2026-08-26, read-only): sqlalchemy @ 0770f6e96
(`dialects/{oracle,mssql,mysql,postgresql}`), pgvector @ e48241b,
pgvector-python @ 60739df, sqlite-vec @ 04d28bd, bm25s @ a213158, lucene
@ 091a987 (`BM25Similarity`, `WordDelimiterGraphFilter`), tantivy @
266a6c4 (`bm25.rs`, `tokenizer_manager.rs`), zoekt @ a9206004
(`index/score.go`), pyserini @ 71072b4.

Papers and docs: Kamphuis, de Vries, Boytsov & Lin, ECIR 2020
(https://cs.uwaterloo.ca/~jimmylin/publications/Kamphuis_etal_ECIR2020_preprint.pdf);
Mühleisen, Samar, Lin & de Vries, SIGIR 2014; Sourcegraph BM25F post;
GitHub code-search post; MariaDB vector overview and RRF page
(https://mariadb.com/docs/server/reference/sql-structure/vectors/optimizing-hybrid-search-query-with-reciprocal-rank-fusion-rrf);
MySQL 9.7 vector functions
(https://dev.mysql.com/doc/refman/9.5/en/vector-functions.html);
Microsoft Learn vector data type, `VECTOR_SEARCH`, RANK/BM25
(https://learn.microsoft.com/en-us/sql/relational-databases/search/limit-search-results-with-rank?view=sql-server-ver17);
Azure SQL hybrid RRF post; Oracle `DBMS_HYBRID_VECTOR`, hybrid search,
vector pool sizing, Oracle Text scoring; PostgreSQL 17 text-search
controls (https://www.postgresql.org/docs/17/textsearch-controls.html);
SQLite FTS5 (https://www.sqlite.org/fts5.html); gvenzl/oci-oracle-free
image details.
