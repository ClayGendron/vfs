# Per-dialect capability matrix and the fused statement

- **Study for**: brief questions 1, 3, 4 and the engine half of 2 of
  [2026-08-26-glean-brief.md](../../2026-08-26-glean-brief.md)
- **Date**: 2026-08-26
- **Method**: every engine claim below is marked **VERIFIED** (executed on a
  running engine in this session; scripts and raw JSON under
  [`engine-matrix/`](engine-matrix/)) or **docs** (vendor documentation, URL
  cited). Nothing is inferred from a spec sheet where a probe could run.
- **Engines run** (all via SQLAlchemy async engines, `uv run`):
  - `pgvector/pgvector:pg17` → PostgreSQL 17.11, pgvector **0.8.6** (one-off
    container, host port 54321). The compose `postgres:17` (17.10) was also
    started: `CREATE EXTENSION vector` fails there — *extension "vector" is
    not available* — so compose cannot serve the vector leg as-is.
  - `mysql:9` → MySQL Community **9.7.2** (one-off, 33064; compose pins 8.4,
    which has no `VECTOR` type at all).
  - `mariadb:11.8` → MariaDB **11.8.9** (one-off, 33063; compose pins 11.4).
  - `mcr.microsoft.com/mssql/server:2025-latest` → SQL Server **2025
    RTM-CU8, 17.0.4075.5**, Developer (one-off, 14331, amd64 under Rosetta).
    Full-text is **not in the image**; it was installed in-container from
    Microsoft's apt repo (`mssql-server-fts 17.0.4075.5-1`) plus a restart.
  - `gvenzl/oracle-free:23-slim` (compose) and `gvenzl/oracle-free:23`
    (regular, one-off, 15211) → both report **"Oracle AI Database 26ai Free
    Release 23.26.2.0.0"** — the `23` tag family *is* 26ai now. The slim
    image has no `CTXSYS` (Oracle Text uninstalled) and no
    `DBMS_HYBRID_VECTOR`; the regular image has both.
  - SQLite **3.50.4** (uv's CPython build, FTS5 compiled in,
    `enable_load_extension` available) + `sqlite-vec` **v0.1.9** (PyPI
    wheel loaded on connect).
- **Sources** (reference checkouts, read-only):
  - sqlalchemy `0770f6e96ba40b192837d5191dd95e9a5838cef3` (2.1 main,
    2026-08-24) — https://github.com/sqlalchemy/sqlalchemy. Runtime in the
    venv is 2.0.46; compile checks ran on 2.0.46, source reading on the
    checkout.
  - pgvector `e48241b4dcc045b18902914f668d03d1d399dfbe` (README at v0.8.6,
    2026-08-19) — https://github.com/pgvector/pgvector
  - pgvector-python `60739dfd6cb9d674f32afa4184d43e6aff9dfbcf` (2026-07-06)
    — https://github.com/pgvector/pgvector-python
  - sqlite-vec `04d28bd21773981e2d266bbf6aa4efbd011eb4f6`
    (v0.1.10-alpha.4, 2026-05-17) — https://github.com/asg017/sqlite-vec
  - Vendor docs: listed in *Sources* at the end.

## Question

For each of Postgres+pgvector, MariaDB 11.8, MySQL 9 community, SQL Server
2025, Oracle 23ai/26ai Free, and SQLite+FTS5+sqlite-vec: what vector type,
distance function, ANN index and dimension caps exist in 2026; what the native
full-text ranking function is and whether it is BM25; whether **one SQL
statement** can carry a vector top-k leg, a lexical top-k leg, reciprocal
rank fusion, a glob-scope allow-list inside each leg, per-entry max-over-chunks
aggregation, and `LIMIT n`; what the honest client-side floor costs where no
server-side distance exists; and how SQLAlchemy 2.1 models each piece.

---

## 1. The fused statement: one portable shape, verified on five engines

The brief's hand-written shape — two ranked CTEs, RRF, scope inside each leg,
max over chunks, `LIMIT n` — runs as **one statement** on Postgres, MariaDB,
SQL Server, Oracle and SQLite, and returns the **same top-5, same scores**
on all five (**VERIFIED**; corpus: 100 entries × 4 chunks, 8-dim synthetic
vectors, lexical target "lantern" planted in entries 30–39, scope
`src/mod3/**` = 10 entry ids, `k_rrf=60`, per-leg `k=20`, `n=5`):

| engine | result (entry_id, MaxP RRF score, chunks hit) | wall (400 chunks) |
|---|---|---|
| Postgres 17.11 + pgvector 0.8.6 | (33, 0.032522, 4) (53, 0.016129, 4) (73, 0.015873, 2) (63, 0.015625, 3) (3, 0.015385, 2) | 29 ms |
| MariaDB 11.8.9 | identical | 6 ms |
| SQL Server 2025 CU8 | identical | 65 ms |
| Oracle 26ai Free 23.26.2 (regular) | identical | 37 ms |
| SQLite 3.50.4 + FTS5 + sqlite-vec 0.1.9 | identical (two variants, §1.2) | 1.5 ms |
| MySQL 9.7.2 | lexical leg only — `VEC_DISTANCE_COSINE` / `DISTANCE()` do not exist | 7 ms |

Entry 33 wins because it is in scope and hit by both legs; entries 31 and 35
(lexical hits, out of scope) never appear; the wall times are on a toy corpus
and prove only that the statement executes.

### 1.1 The portable skeleton

The MariaDB and Azure SQL reference queries both fuse with a `FULL OUTER
JOIN` (MariaDB emulates it with two `LEFT JOIN`s and a `UNION`). The shape
below replaces that with `UNION ALL` + `GROUP BY chunk_id` + `SUM`, which is
exactly RRF (a chunk absent from a leg contributes 0) and needs nothing beyond
CTEs, window functions, `UNION ALL`, `GROUP BY` and a row limit — all present
on all six engines (window functions: Postgres, MySQL 8+, MariaDB 10.2+, SQL
Server, Oracle, SQLite 3.25+). Only the three leg expressions and the
row-limit spelling vary per dialect (§1.2):

```sql
WITH vec_top AS (                       -- vector leg, scoped, top-kv
  SELECT c.id AS chunk_id, c.entry_id, <DIST(c.embedding, :q)> AS dist
  FROM chunks c JOIN <SCOPE> s ON s.id = c.entry_id
  WHERE c.embedding IS NOT NULL
  ORDER BY dist <LIMIT :kv>
), vec AS (
  SELECT chunk_id, entry_id, ROW_NUMBER() OVER (ORDER BY dist) AS rnk FROM vec_top
), lex_top AS (                         -- lexical leg, scoped, top-kl
  SELECT c.id AS chunk_id, c.entry_id, <SCORE(c.content, :qt)> AS score
  FROM chunks c JOIN <SCOPE> s ON s.id = c.entry_id
  WHERE <MATCH(c.content, :qt)>
  ORDER BY score DESC <LIMIT :kl>
), lex AS (
  SELECT chunk_id, entry_id, ROW_NUMBER() OVER (ORDER BY score DESC) AS rnk FROM lex_top
), legs AS (                            -- reciprocal rank fusion, 1/(k+rank)
  SELECT chunk_id, entry_id, 1.0 / (:k + rnk) AS rrf FROM vec
  UNION ALL
  SELECT chunk_id, entry_id, 1.0 / (:k + rnk) AS rrf FROM lex
), per_chunk AS (
  SELECT chunk_id, entry_id, SUM(rrf) AS rrf FROM legs GROUP BY chunk_id, entry_id
)
SELECT entry_id, MAX(rrf) AS score, COUNT(*) AS chunks_hit   -- MaxP over chunks
FROM per_chunk GROUP BY entry_id
ORDER BY score DESC, entry_id <LIMIT :n>
```

Ranking happens in a CTE *above* the `LIMIT`ed leg (`vec_top` → `vec`) rather
than as a window over the same `ORDER BY`: with the window inside the leg the
planner must sort everything before limiting, which defeats an ANN index scan
(pgvector's plan for the bare leg is `Index Scan using hnsw ... Order By`;
**VERIFIED**). SQLAlchemy Core compiles this skeleton with the right limit
spelling per dialect — `TOP n` for SQL Server, `FETCH FIRST n ROWS ONLY` for
Oracle, `LIMIT n` elsewhere (**VERIFIED**, `select(...).cte()`,
`func.row_number().over()`, `union_all`, `.limit()`).

### 1.2 The leg expressions per dialect (all VERIFIED unless noted)

| dialect | `DIST` (cosine) | query bind | `MATCH` / `SCORE` | row limit |
|---|---|---|---|---|
| Postgres | `c.embedding <=> CAST(:q AS vector)` | JSON text `'[…]'` | `c.tsv @@ plainto_tsquery('english', :qt)` / `ts_rank_cd(c.tsv, plainto_tsquery(...))` (stored generated `tsvector` column + GIN) | `LIMIT` |
| MariaDB | `VEC_DISTANCE_COSINE(c.embedding, VEC_FromText(:q))` | JSON text | `MATCH(c.content) AGAINST (:qt IN NATURAL LANGUAGE MODE)` in both `WHERE` and select list (optimizer runs it once) | `LIMIT` |
| MySQL 9 | **none** (function absent) | — | same as MariaDB | `LIMIT` |
| SQL Server | `VECTOR_DISTANCE('cosine', c.embedding, CAST(:q AS VECTOR(n)))` | JSON text | `JOIN FREETEXTTABLE(chunks, content, :qt) ft ON ft.[KEY] = c.id` / `ft.[RANK]` (or `CONTAINSTABLE`) | `TOP (:n)` |
| Oracle | `VECTOR_DISTANCE(c.embedding, TO_VECTOR(:q), COSINE)` | JSON text (or `array.array` via python-oracledb) | `CONTAINS(c.content, :qt, 1) > 0` / `SCORE(1)` (CONTEXT index, `sync (on commit)`) | `FETCH FIRST :n ROWS ONLY` |
| SQLite (vec0) | `v.embedding MATCH :q AND k = :kv AND v.rowid IN (<scope subquery>)` on the `vec0` table; `v.distance` | JSON text | `fts MATCH :qt AND f.rowid IN (<scope subquery>)` / `bm25(fts)` (ascending — FTS5 negates BM25) | `LIMIT` |
| SQLite (scalar) | `vec_distance_cosine(c.embedding, :q)` over a BLOB column, ordinary join | JSON text vs `vec_f32` BLOB | as above | `LIMIT` |

Notes that matter for the builder:

- **Scope inside the leg works everywhere** as an `IN`-list on `entries.id`
  (expanding bind; `membership_budget` applies — see §5) or a join to a scope
  CTE. On SQLite the scope is pushed *into* the vec0 KNN and the FTS5 MATCH
  via `rowid IN (subquery)` (**VERIFIED**; plan shows `SCAN v VIRTUAL TABLE
  INDEX 0:3…` with the list subquery). The two SQLite variants — vec0 KNN
  vs. scalar `vec_distance_cosine` over a plain BLOB column — return
  identical rows.
- **InnoDB full-text indexes are visible only after commit** (**VERIFIED**:
  `MATCH … AGAINST` returned 0.0 for every row when the inserts were in an
  open transaction; committed, the scores are 3.0/2.0/1.0 for 3/2/1
  occurrences). Any test or reindex path that queries in the writing
  transaction sees nothing.
- **SQL Server**: full-text is refused in `master`/`tempdb`/`model` (error
  9966) — the conformance harness's `master` URL cannot host the lexical leg;
  a full-text catalog and a unique key index are required; population is
  **asynchronous** (the probe polled `FULLTEXTCATALOGPROPERTY(...,
  'PopulateStatus')` and a real query for 4 s before rows appeared,
  **VERIFIED**). `PREVIEW_FEATURES` is likewise refused on system databases
  (error 12122).
- **Oracle**: creating the CONTEXT index took 2.6 s on an empty table;
  `SCORE(1)` needs the same label as the `CONTAINS(..., 1)` predicate. The
  probe granted `CTXAPP` to the app user first; whether the index creates
  without it was not tested.
- **pyodbc sees SQL Server vectors as JSON text** (`'[8.1940800e-001,…]'`,
  declared type `vector`, 40 bytes for 8 dims = 8 + 4·n; **VERIFIED**) —
  the July study's "JSON is the documented client protocol" holds on the
  real engine.

### 1.3 Oracle's and MariaDB's engine primitives, compared with the hand-written shape

- **MariaDB's documented RRF query** (docs) is the same hand-written shape:
  two `LIMIT 10` legs (`VEC_DISTANCE_EUCLIDEAN` and `MATCH … AGAINST`),
  `1 / (@k + RANK() OVER (...))` per leg, a two-sided `LEFT JOIN` + `UNION`
  standing in for a full outer join, `ORDER BY total_rrf DESC LIMIT 10`.
  There is no fusion primitive; the page is a worked example of plain SQL.
  Our `UNION ALL`/`GROUP BY` form is equivalent and shorter.
- **Azure SQL's RRF post** (docs) is again the same shape: `FREETEXTTABLE`
  with `RANK() OVER (ORDER BY ft_rank DESC)`, `VECTOR_DISTANCE` with
  `RANK() OVER (ORDER BY cosine_distance)`, `FULL OUTER JOIN`,
  `COALESCE(1.0/(@k + rank), 0)` summed. It uses temp tables rather than
  CTEs; a CTE version executes on SQL Server 2025 (**VERIFIED** above).
- **Oracle `DBMS_HYBRID_VECTOR.SEARCH`** is a real primitive (RSF default,
  RRF, WRRF; `search_fusion` UNION/INTERSECT/…; document vs chunk mode with
  `aggregator` MAX/AVG/…; `rank_penalty` defaults vector=1, text=5;
  `filter_by` JSON predicates; returns a JSON array joined back through
  `JSON_TABLE` + `CHARTOROWID`; docs). **It cannot use vfs's embeddings**:
  a hybrid vector index is created on a *text* column and embeds the text
  itself with an in-database ONNX model — `CREATE HYBRID VECTOR INDEX … ON
  chunks(content)` without a model fails with `DRG-51504: need to specify
  model name when using hybrid vector index`, and on the `VECTOR` column
  with `ORA-02327: cannot create index on expression with data type VECTOR`
  (**VERIFIED**, regular image). The docs confirm "Currently, only ONNX
  in-database embedding models are supported" and the index chunks and
  vectorizes the column. It also requires Oracle Text (absent from the slim
  image). For a backend whose embedding provider lives in Storage (R4) it
  is the wrong seam; the hand-written statement over our own `VECTOR`
  column plus a CONTEXT index is the Oracle path.

---

## 2. Per-engine ground truth

### 2.1 PostgreSQL 17 + pgvector 0.8.6

- **Type/caps** (**VERIFIED**): `vector(16000)` creates, `vector(16001)`
  fails ("dimensions for type vector cannot exceed 16000"); HNSW on
  `vector(2001)` fails ("column cannot have more than 2000 dimensions for
  hnsw index"), `vector(2000)` indexes; `halfvec(4000)` indexes, `halfvec
  (4001)` does not. Source constants agree: `VECTOR_MAX_DIM 16000`,
  `HNSW_MAX_DIM 2000`, `IVFFLAT_MAX_DIM 2000`, `HALFVEC_MAX_DIM 16000`
  (`pgvector/src/*.h`). A 3,072-dim model can be stored and exact-scanned
  as `vector`, but ANN-indexed only as `halfvec`.
- **Distance**: `<=>` cosine, `<->` L2, `<#>` negative inner product, `<+>`
  L1 (**VERIFIED** `<=>`). `ts_rank` and `ts_rank_cd` execute (0.061 /
  0.100 on the toy row).
- **ANN and scope** (**VERIFIED** at 50,000 chunks over 5,000 entries,
  8-dim, HNSW cosine): the planner arbitrates per query. Scope = 10 entries
  → `Index Scan using glean_chunks_hnsw … Filter: entry_id = ANY(...)`,
  381–481 rows removed by the filter to produce 10–20 hits (this is the
  post-filter recall trap; `hnsw.iterative_scan = relaxed_order` keeps
  scanning until the limit fills). Scope = half the corpus (`entry_id
  BETWEEN`) → `Bitmap Index Scan` on the scope index + `top-N heapsort`
  (exact, 25,000 rows). Scope via a join on `entries.path LIKE 'src/mod3/%'`
  → `Seq Scan` + hash join + sort (exact). So on Postgres the scope predicate
  *is* honoured inside the leg and the engine chooses ANN-then-filter or
  exact-over-scope on cost. Recall is 1.0 whenever it picks the exact plan
  and index-dependent otherwise — the honesty record must read the plan or
  the GUC, not assume.
- **Lexical**: `ts_rank` "ranks vectors based on the frequency of their
  matching lexemes"; `ts_rank_cd` is Clarke–Cormack–Tudhope cover density;
  normalization is a bitmask (0 ignore length, 1 log-length, 2 length, …);
  "**the ranking functions do not use any global information**" — no IDF,
  **not BM25** (docs). Tokenizer/stemmer control is the `regconfig`
  (`'english'`, `'simple'`, custom dictionaries). Scoping before scoring is
  an ordinary join (**VERIFIED**). A stored generated `tsvector` column with
  a GIN index is the indexed form (**VERIFIED** DDL).

### 2.2 MariaDB 11.8.9 (community, GA vector search)

- **Type/caps** (**VERIFIED**): `VECTOR(n)` float32; `vector(65536)` fails
  with "Column length too big for column 'v' (max = 16383)"; `vector(16383)`
  then fails with **"Row size too large … 65535"** — the InnoDB row-size
  cap (16,383 × 4 = 65,532 bytes plus overhead) binds before the column
  cap. The docs state no dimension limit; the practical ceiling is just
  under 16,383 and shrinks with every other non-BLOB column in the row.
- **Distance** (**VERIFIED**): `VEC_DISTANCE_COSINE`, `VEC_DISTANCE_EUCLIDEAN`,
  and `VEC_DISTANCE` (adapts to the index's metric). No dot product (docs).
  Cosine arrived in 11.7; 11.8 is the first LTS with vectors (docs).
- **ANN index** (**VERIFIED**): `VECTOR INDEX (embedding) DISTANCE=cosine`
  (MHNSW; `M` 3–200; column must be `NOT NULL`). Plan for the bare
  `ORDER BY VEC_DISTANCE_COSINE(...) LIMIT 20` is `type=index, key=embedding`
  (the vector index). **With a scope predicate (`WHERE entry_id IN (...)`)
  the plan is `range` on `entry_id` + `Using filesort`** — the vector index
  is not used; the leg is an exact scan over the scoped rows. The docs say
  the index is used only with the bare distance function in `ORDER BY` with
  `LIMIT`. There is no filtered-ANN mode; a scoped glean on MariaDB is
  exact by construction (recall 1.0, cost ∝ scope size), and ANN applies
  only to unscoped queries.
- **Lexical** (**VERIFIED**): InnoDB `FULLTEXT`, `MATCH … AGAINST (... IN
  NATURAL LANGUAGE MODE)` scores 3.0/2.0/1.0 for tf 3/2/1 on a one-term
  query; index used inside a scoped join. Ranking is TF-IDF-style
  ("weighted according to its significance in the collection"; no length
  normalization documented) — **not BM25**. Tokenizer control:
  `innodb_ft_min_token_size` (default 3 — "fox" matched), stopword table,
  ngram/mecab parsers. The MyISAM 50 % threshold does not apply to InnoDB
  (docs, MySQL manual; MariaDB inherits the InnoDB implementation).

### 2.3 MySQL 9.7.2 community

- **Type/caps** (**VERIFIED**): `VECTOR(n)`; `vector(16383)` creates (stored
  BLOB-like, so no row-size issue); `VECTOR_DIM`, `VECTOR_TO_STRING`,
  `STRING_TO_VECTOR` work; `LENGTH(v)` = 4·n.
- **Distance**: `DISTANCE()` and `VECTOR_DISTANCE()` both fail with
  "FUNCTION vfs.distance does not exist" (**VERIFIED**). The manual (9.7):
  "DISTANCE() is available only for users of MySQL HeatWave on OCI and
  MySQL AI; it is not included in MySQL Commercial or Community
  distributions" (docs).
- **Index**: `CREATE INDEX … (v)` fails with error 6134 "Non-scalar (e.g.,
  vector) column 'v' cannot be used as key" (**VERIFIED**). No ANN of any
  kind.
- **Driver gap** (**VERIFIED**): pymysql/aiomysql cannot decode the raw
  `VECTOR` wire type — `SELECT vb` raises `UnicodeDecodeError`, and
  `CAST(vb AS BINARY)` desynchronises the connection ("Packet sequence
  number wrong"). `HEX(vb)` and `TO_BASE64(vb)` work. The native type buys
  nothing for search and costs a transport workaround; a `VARBINARY`
  column of packed float32 is strictly better on MySQL.
- **Lexical**: identical to MariaDB (InnoDB `FULLTEXT`; plan `Full-text
  index search on c … Filter: entry_id in (...)`, **VERIFIED**).
- **Consequence**: the fused statement is impossible; the statement carries
  the lexical leg only, and the vector leg is the client-side floor (§4).

### 2.4 SQL Server 2025 (17.x) RTM-CU8

- **Type/caps** (**VERIFIED**): `VECTOR(1998)` creates, `VECTOR(1999)` fails
  ("exceeds the maximum allowed (1998)"). `float16` base type is
  preview-gated (docs).
- **Distance** (**VERIFIED**): `VECTOR_DISTANCE('cosine' | 'euclidean' |
  'dot', a, b)` GA; exact `TOP (k) … ORDER BY VECTOR_DISTANCE(...)` with a
  scope join works and is what the fused statement uses.
- **ANN** (**VERIFIED**, preview): with `PREVIEW_FEATURES = ON` (user
  database only), `CREATE VECTOR INDEX … WITH (METRIC='cosine',
  TYPE='diskann')` builds on 400 rows (0.4–0.7 s) and shows as
  `type_desc = VECTOR` in `sys.indexes`. **The table becomes read-only**:
  `UPDATE` and `INSERT` fail with error 42231 "Data modification statement
  failed because table has a vector index on it". `VECTOR_SEARCH(TABLE=…,
  COLUMN=…, SIMILAR_TO=@qv, METRIC='cosine', TOP_N=5)` works only with a
  *declared variable* (`SIMILAR_TO = CAST(:q AS VECTOR(8))` is a syntax
  error — the docs say "must be a variable or a column"), so the leg needs
  a `DECLARE @qv VECTOR(n) = CAST(:q AS VECTOR(n));` batch prefix. A `WHERE
  t.entry_id IN (...)` on `VECTOR_SEARCH` is a **post-filter** (1 of 5 rows
  survived; docs call this "earlier version" behaviour). The newer `SELECT
  TOP (n) WITH APPROXIMATE` syntax with iterative filtering and full DML is
  rejected on this build ("Incorrect syntax near 'approximate'") — the
  docs say the latest index version "is only available in Azure SQL
  Database and SQL database in Fabric currently". `VECTOR_SEARCH` also
  works inside a CTE (**VERIFIED**). Verdict: on-prem 2025 DiskANN is not
  usable for a table that is written to; the exact leg is the SQL Server
  path.
- **Lexical** (**VERIFIED** after installing `mssql-server-fts`): `RANK` is
  0–1000 and "only a relative order … typically differ each time the query
  runs"; **`FREETEXTTABLE` ranking is Okapi BM25** with `k1=1.2, b=0.75,
  k3=8.0` and Robertson–Sparck Jones weights (docs, formula quoted on the
  RANK page); `CONTAINSTABLE` ranks by `HitCount * 16 * log2((2 +
  IndexedRowCount)/KeyRowCount) / MaxOccurrence` with `MaxOccurrence`
  bucketed into 32 ranges (docs). `CONTAINSTABLE(..., 'lantern')` returned
  `RANK = 192` for the tf=3 chunks. Tokenizer control is the per-column
  `LANGUAGE` word breaker (LCID 1033 used); stemming is `FORMSOF
  (INFLECTIONAL, …)` in `CONTAINS`, implicit in `FREETEXT`. Scoping before
  scoring is a join on `[KEY]` (**VERIFIED**), and `top_n_by_rank` caps the
  TVF itself.

### 2.5 Oracle 26ai Free 23.26.2 (the `23` tags) — regular image

- **Type/caps** (**VERIFIED**): `VECTOR(65535, FLOAT32)` creates; `65536`
  fails with `ORA-51801 … integer between 1 and 65535`.
- **Distance** (**VERIFIED**): `VECTOR_DISTANCE(a, b, COSINE)`; `TO_VECTOR
  ('[…]')` binds from JSON text; pgvector-style operators `<=>`, `<->`,
  `<#>` are what SQLAlchemy's in-tree comparators emit.
- **ANN** (**VERIFIED**): on the Free image `vector_memory_size = 0`, and
  HNSW creation fails with `ORA-51962: The vector memory area is out of
  space`. Setting it needs `ALTER SYSTEM SET vector_memory_size = 256M
  SCOPE=SPFILE` **at the CDB root** (`service_name=FREE`; the same statement
  inside `FREEPDB1` was silently ineffective) and a restart. After that:
  `CREATE VECTOR INDEX … ORGANIZATION INMEMORY NEIGHBOR GRAPH DISTANCE COSINE
  WITH TARGET ACCURACY 95` builds in 0.9 s; the bare `FETCH APPROX FIRST 5
  ROWS ONLY WITH TARGET ACCURACY 90` plans as `VECTOR INDEX HNSW SCAN`.
  **With a scope predicate (`WHERE entry_id IN (...)`) the same APPROX query
  plans as `TABLE ACCESS FULL` + `SORT ORDER BY STOPKEY`** — exact, index
  unused — and identically for the IVF index (`ORGANIZATION NEIGHBOR
  PARTITIONS`, 1.2 s build). Without any index, `FETCH APPROX` silently
  runs exact (`TABLE ACCESS FULL`; **VERIFIED**), which the SQLAlchemy docs
  also state ("the query returns exact results"). Oracle documents
  pre/in-filter hints (`filter_type PRE_W/IN_W/…` in the hybrid API); they
  were not exercised here.
- **Lexical** (**VERIFIED**): `CONTAINS(content, :q, 1) > 0` with `SCORE(1)`
  on a `CTXSYS.CONTEXT` index (`sync (on commit)`; `CTX_DDL.SYNC_INDEX`
  also used). Scores were 18 for tf=3 chunks. Oracle Text "uses an inverse
  frequency algorithm based on Salton's formula … the query term must occur
  frequently in the document but infrequently in the document set" — 0–100
  relative, **not BM25**, no length normalization documented (docs).
  Tokenizer control is the lexer preference (`BASIC_LEXER`,
  `WORLD_LEXER`, stemmer/fuzzy in the wordlist). Scoping before scoring is
  an ordinary join (**VERIFIED**).
- **Hybrid**: `DBMS_HYBRID_VECTOR` exists (CTXSYS package + public synonym)
  in the regular image only; see §1.3 for why it is not our seam.

### 2.6 SQLite 3.50.4 + FTS5 + sqlite-vec 0.1.9

- **Vector** (**VERIFIED**): `vec0(embedding float[8] distance_metric=cosine)`
  virtual table, KNN via `embedding MATCH :q AND k = :kv`, `rowid IN
  (subquery)` prefilter honoured inside the KNN; also scalar
  `vec_distance_cosine(blob, json)` over an ordinary BLOB column (exact scan
  in C with arbitrary SQL). `vec_f32('[…]')` packs JSON to float32 bytes.
  vec0 is brute force (no ANN); sqlite-vec's own README lists DiskANN/IVF
  only as in-progress. It is a loadable extension: the probe loads it in a
  SQLAlchemy `connect` event through the aiosqlite adapter's raw `sqlite3`
  connection (`dbapi_conn._connection._conn`), which is the pattern a
  `sqlite_native` opt-in would use.
- **Lexical** (**VERIFIED**): external-content FTS5 table
  (`content='chunks', content_rowid='id'`, `tokenize='porter unicode61'`),
  `bm25(fts)` returns **negative** values (−3.27 for the tf=3 chunks; "the
  FTS5 implementation of BM25 multiplies the result by −1" so `ORDER BY
  rank` ascending is best-first; `k1=1.2, b=0.75` hard-coded; per-column
  weights as extra args; docs). Tokenizers: `unicode61` (categories,
  tokenchars, separators, remove_diacritics), `ascii`, `porter` wrapper,
  `trigram` (substring/GLOB/LIKE). `rowid IN (...)` prefilter works before
  ranking (**VERIFIED**). It is the only engine besides SQL Server's
  `FREETEXTTABLE` whose native score is BM25.

---

## 3. Capability matrix (2026-08-26)

| | Postgres 17 + pgvector 0.8.6 | MariaDB 11.8.9 | MySQL 9.7.2 community | SQL Server 2025 CU8 | Oracle 26ai Free 23.26.2 | SQLite 3.50 + FTS5 + sqlite-vec 0.1.9 |
|---|---|---|---|---|---|---|
| vector type | `vector`/`halfvec`/`bit`/`sparsevec` (ext) | `VECTOR(n)` float32 | `VECTOR(n)` float32 | `VECTOR(n)` float32 (`float16` preview) | `VECTOR(n, FLOAT32/64/INT8/BINARY)` dense/sparse | `vec0` virtual table or BLOB |
| storage dim cap | 16,000 (V) | 16,383 col cap, InnoDB 65,535-byte row cap binds first (V) | 16,383 (V) | 1,998 (V) | 65,535 (V) | none tested |
| server-side distance | `<=>` `<->` `<#>` `<+>` (V) | `VEC_DISTANCE_COSINE/EUCLIDEAN/VEC_DISTANCE` (V) | **none** (V) | `VECTOR_DISTANCE(cosine/euclidean/dot)` GA (V) | `VECTOR_DISTANCE(a,b,COSINE…)` (V) | `vec_distance_cosine/l2/l1`, vec0 KNN (V) |
| ANN index | HNSW/IVFFlat, ≤2,000 dims (`halfvec` ≤4,000) (V) | MHNSW `VECTOR INDEX … DISTANCE=cosine` (V) | **none** — vector column "cannot be used as key" (V) | DiskANN, **preview**, table becomes read-only, `TOP_N` syntax only (V) | HNSW / IVF, needs vector pool (`vector_memory_size`, CDB-level) (V) | none (brute force) |
| ANN + scope predicate | planner arbitrates: HNSW+filter for small scope, exact for large (V @50k) | index **not used** when scoped → exact scan (V) | n/a | `VECTOR_SEARCH` post-filters (V) | HNSW/IVF **not used** when scoped → `TABLE ACCESS FULL` (V) | vec0 honours `rowid IN` prefilter (V) |
| native FTS + rank fn | `to_tsvector/@@`, `ts_rank`, `ts_rank_cd` (V) | InnoDB `MATCH…AGAINST` (V) | InnoDB `MATCH…AGAINST` (V) | `FREETEXTTABLE`/`CONTAINSTABLE` `RANK` (V, after installing FTS) | Oracle Text `CONTAINS`/`SCORE` (V, regular image) | FTS5 `bm25()`/`rank` (V) |
| is it BM25? | **no** — frequency/cover density, "no global information" (docs) | **no** — TF-IDF-style (docs) | **no** (docs) | `FREETEXTTABLE`: **yes**, Okapi BM25 k1=1.2 b=0.75; `CONTAINSTABLE`: no (docs) | **no** — Salton inverse frequency (docs) | **yes**, k1=1.2 b=0.75, negated (docs) |
| tokenizer control | `regconfig` dictionaries/stemmers | `innodb_ft_min_token_size`, stopwords, ngram/mecab | same | per-column `LANGUAGE` word breaker, `FORMSOF` | lexer/wordlist preferences | `unicode61`/`ascii`/`porter`/`trigram` options |
| scope join before scoring | yes (V) | yes, FT index still used (V) | yes (V) | yes, join on `[KEY]` (V) | yes (V) | yes, `rowid IN` (V) |
| one fused statement | **yes** (V) | **yes** (V) | lexical leg only (V) | **yes** (V) | **yes** (V) | **yes** (V) |
| vector-leg tier | native ANN or exact | native ANN (unscoped) / exact (scoped) | **client floor** | exact (ANN preview, read-only) | native ANN (unscoped) / exact (scoped) | exact in C |

(V) = VERIFIED this session.

A cross-cutting fact for the lexical leg: on every engine the IDF-type
statistics are **corpus-global** — scoping by join changes which rows are
ranked, never the term weights. Under RRF only ranks enter the fusion, so
this is harmless for the fused statement; it matters only if a leg's raw
score were ever compared across scopes or engines (it should not be).

---

## 4. The floor: client-side exact scan on MySQL community (and GENERIC)

Benchmark (**VERIFIED**, `bench_floor_mysql.py`, MySQL 9.7.2 in Docker on
this Mac, aiomysql, 384-dim, best of 3 per cell, top-10 by cosine in numpy;
`json` = `TEXT` column holding `json.dumps(list[float])` exactly as
`VectorType` serializes today; `bin` = native `VECTOR(384)` shipped as
`TO_BASE64(vb)` because pymysql cannot read the raw wire type):

| N vectors | bytes/vector | fetch | parse | score | **total** |
|---|---|---|---|---|---|
| 1,000 json | 7,975 | 0.012 s | 0.080 s | 0.0003 s | **0.092 s** |
| 1,000 bin | 1,536 (+33 % base64) | 0.005 s | 0.003 s | 0.0003 s | **0.008 s** |
| 10,000 json | 7,975 | 0.092 s | 0.814 s | 0.0017 s | **0.907 s** |
| 10,000 bin | 1,536 | 0.039 s | 0.027 s | 0.0018 s | **0.068 s** |
| 50,000 json | 7,976 | 0.446 s | 4.236 s | 0.0095 s | **4.692 s** |
| 50,000 bin | 1,536 | 0.190 s | 0.134 s | 0.0083 s | **0.332 s** |

Readings:

- **`json.loads` is the binding cost**, not the wire and not the math: at
  50k it is 90 % of the JSON total. The July estimate ("~1–2 s at 10k")
  was pessimistic on fetch and optimistic on parse; the measured JSON floor
  is ≈ 0.9 s per 10k vectors, ≈ 4.7 s per 50k — linear.
- **Packed float32 is 14× faster end to end at 50k** and 5.2× smaller on
  disk (Python's `repr(float)` emits ~20 bytes per component; the July
  memo's "~12 bytes" understated it). Scoring 50k × 384 in numpy is 8 ms;
  the arithmetic never matters below ~1M.
- **Honest ceiling** for an interactive glean (≈ 1 s budget on the vector
  leg alone): **≈ 10k scoped chunk vectors with JSON text, ≈ 150k with
  packed binary** at 384 dims; divide by 4 for 1,536 dims. The floor
  degrades linearly and never in correctness (recall 1.0). Insert cost at
  the floor is also visible: 50k rows of both encodings took 34 s through
  `executemany` batches of 500 — the JSON column is most of that payload.
- **Where fusion happens on the floor**: the statement carries the lexical
  leg only (top-kl chunk ids with ranks, **VERIFIED** on MySQL); the vector
  leg is `SELECT id, entry_id, <binary> FROM chunks WHERE <scope>` scored in
  numpy; RRF and MaxP run in Python over two rank lists of ≤ k rows each.
  The Python fuser is the same function the cross-mount merge needs, so
  the floor costs no second algorithm.

---

## 5. Scope, binds and budgets in the fused statement

- The scope allow-list is one expanding `IN` bind per leg (two per
  statement) — **VERIFIED** on all engines with 10 ids; Oracle's plan shows
  the ten `:ids_n` binds. Under `membership_budget`, the ceiling per
  statement is the tighter of `in_list_budget` (Oracle 1,000, SQL Server
  2,100, MySQL/MariaDB 65,535, Postgres 32,766, GENERIC 1,000) and the
  parameter budget, and **the list appears in both legs**, so the per-leg
  list is at most `(budget − fixed binds) / 2` elements in one statement.
- A scope wider than one chunk **breaks single-statement fusion**: RRF
  needs each leg's global rank over the whole scope, and a top-k taken per
  id-chunk is not the top-k of the union. Two lawful shapes: (a) express the
  scope as a *predicate* rather than a list — path-prefix ranges / segment
  joins exactly as grep's `_pushdown_terms` does (ADR 040) — so one
  statement covers any scope size (the Postgres `path LIKE 'src/mod3/%'`
  join plan above is this shape, exact); (b) run each leg per chunk with
  `ORDER BY … LIMIT k`, merge the chunks' top-k client-side into a global
  top-k per leg, and fuse in Python. (a) is the design; (b) is the fallback
  for observation-piped scopes (brief gap 14) that are lists by nature.
- Bind budgets are otherwise generous: the fused statement carries ~8 scalar
  binds (`q`, `qt`, `kv`, `kl`, `k`, `n`) plus the two lists; the query
  vector is one bind (JSON text on every engine; `array.array` optional on
  Oracle).

---

## 6. How SQLAlchemy models each piece (2.1 checkout `0770f6e96`; compile checks on 2.0.46)

| piece | Postgres | Oracle | SQL Server | MySQL / MariaDB | SQLite |
|---|---|---|---|---|---|
| vector column type | **pgvector-python** `VECTOR/HALFVEC/BIT/SPARSEVEC` (`UserDefinedType`, `get_col_spec` → `VECTOR(n)`, JSON-text bind/result processors) | **in-tree** `oracle.VECTOR(dim, storage_format, storage_type)` since 2.0.41; binds `array.array`; `SparseVector` (2.0.43+) | **none** in 2.1 (grep of `dialects/mssql` finds no vector) | **none** in 2.1 (`dialects/mysql` has nothing) | none |
| distance comparators | `.l2_distance/.max_inner_product/.cosine_distance/.l1_distance` via `self.op('<=>', return_type=Float)` | `.l2_distance/.inner_product/.cosine_distance` emitting `<->`/`<#>`/`<=>` (`oracle/vector.py:358-366`) | `func.vector_distance('cosine', col, cast(q, VECTOR))` — plain `func`, arg order engine-defined | `func.vec_distance_cosine(col, func.vec_fromtext(q))` — plain `func` | `func.vec_distance_cosine(col, q)` — plain `func` |
| ANN DDL | `Index(..., postgresql_using='hnsw', postgresql_with={'m':16,'ef_construction':64}, postgresql_ops={'embedding':'vector_cosine_ops'})` (pgvector-python README) | `Index(..., oracle_vector=VectorIndexConfig(index_type=HNSW/IVF, distance=…, accuracy=…, hnsw_neighbors=…))` (`oracle/base.py:906-930`, `_build_vector_index_config`) | none — raw `CREATE VECTOR INDEX` DDL | MariaDB `VECTOR INDEX (col) DISTANCE=cosine` is table-DDL, not `Index()` — raw | raw `CREATE VIRTUAL TABLE … USING vec0` |
| approximate fetch | none needed (`ORDER BY <=> LIMIT`) | `select(...).fetch(k, oracle_fetch_approximate=True)` → `FETCH APPROX FIRST k ROWS ONLY` (**VERIFIED** compiles on 2.0.46); `TARGET ACCURACY` not modelled | none — `VECTOR_SEARCH` TVF needs `text()` (and a `DECLARE` prefix) | n/a | n/a |
| `col.match(q)` compiles to | `col @@ plainto_tsquery(q)` (`postgresql_regconfig` modifier) | `CONTAINS(col, q)` — **no label**, so `SCORE(n)` cannot be referenced | `CONTAINS(col, q)` — the predicate form, **no RANK** | `MATCH (col) AGAINST (q IN BOOLEAN MODE)`; `mysql.match(col, against=q).in_natural_language_mode()` for the scored form (**VERIFIED**) | `col MATCH ?` (column form; the table-valued `fts MATCH ?` needs `literal_column`) |
| FTS types/functions | `TSVECTOR`, `TSQUERY`, `func.to_tsvector/to_tsquery/plainto_tsquery/phraseto_tsquery/websearch_to_tsquery` (`postgresql/ext.py`, typed), `ts_rank_cd` via `func`, generated column via `Computed()` | none beyond `match` | none — `FREETEXTTABLE`/`CONTAINSTABLE` are TVFs (`func.freetexttable(...).table_valued('KEY','RANK')` is the Core idiom; not verified here) | `match` construct | none |
| fusion skeleton | Core: `.cte()`, `func.row_number().over()`, `union_all`, `.group_by`, `.limit()` → `LIMIT` | same → `FETCH FIRST n ROWS ONLY` (**VERIFIED** compile) | same → `TOP n` (**VERIFIED** compile) | same → `LIMIT` | same → `LIMIT` |

What needs custom compilation (or `text()`) in vfs, concretely:

1. **Two dialect-local vector types** — `VECTOR(n)` for SQL Server (JSON-text
   bind/result, as pyodbc sees it) and MariaDB (bind through
   `VEC_FromText`, read through `VEC_ToText` or raw bytes) — as
   `UserDefinedType`s selected from `VectorType.load_dialect_impl`, the
   pattern already used for `postgres_native`. Oracle needs no new type.
   MySQL should stay on `LargeBinary` (§2.3).
2. **A distance-expression factory** keyed by dialect name: operator
   comparator (pg, oracle) vs `func.*` with engine-specific argument order
   (mssql `('cosine', a, b)`; mariadb `(a, b)`; sqlite `(a, b)`), and *no
   expression* for mysql/generic (the leg is client-side).
3. **A lexical predicate + score pair** per dialect: `match()` is only the
   predicate on four of six dialects and lacks Oracle's label and SQL
   Server's rank; the scored forms are `mysql.match` (in-tree),
   `func.ts_rank_cd` (pg), a small `CONTAINS(col, q, 1)`/`SCORE(1)`
   `FunctionElement` pair for Oracle, a `table_valued` `FREETEXTTABLE` join
   for SQL Server, and `func.bm25(literal_column('fts'))` for SQLite.
4. **DDL outside `Index()`**: MariaDB's `VECTOR INDEX` table option,
   SQLite's `vec0`/`fts5` virtual tables, SQL Server's full-text catalog +
   `CREATE FULLTEXT INDEX` + async population wait, Oracle's `CONTEXT` index
   with `sync (on commit)`, Postgres's generated `tsvector` column + GIN.
5. **Connection hooks**: sqlite-vec extension load on `connect`.

---

## 7. Bearing on vfs

**Recommendation.**

1. **Ship one fused statement built with Core from §1.1**, with the three
   leg expressions and the row limit as the only dialect variation, on
   Postgres, MariaDB, SQL Server, Oracle and SQLite. RRF (`1/(k+rank)`) and
   MaxP (`GROUP BY entry_id, MAX`) live in SQL on these five. This is
   verified to produce identical rankings across all five engines on the
   same data — the determinism the conformance suite can pin (gap 8), with
   `ORDER BY score DESC, entry_id` as the stable tie-break.
2. **Keep the Python fuser as a first-class path, not a fallback**: MySQL
   community and GENERIC run the lexical leg in SQL and the vector leg as a
   scoped exact scan scored in numpy, then fuse in Python; the same fuser
   merges mounts. Every fused result records which tier served each leg
   (native ANN / native exact / client floor) — on Postgres and Oracle
   that is a plan-level fact, on MariaDB and SQL Server it follows from
   whether a scope was present.
3. **Store embeddings as packed float32 at the floor** — a `LargeBinary`
   of `array('f').tobytes()` replaces JSON text in `VectorType`'s portable
   path (14× at 50k, 5× smaller); native types only where SQLAlchemy or a
   small `UserDefinedType` models them (pg `vector`, Oracle `VECTOR`, SQL
   Server `VECTOR(n)`, MariaDB `VECTOR(n)`), never MySQL's `VECTOR`.
4. **Treat ANN as opt-in per mount and unscoped-only in practice**: a scope
   predicate disables the vector index on MariaDB and Oracle (exact scan),
   post-filters on SQL Server 2025 on-prem (whose index also makes the
   table read-only — do not ship DiskANN there), and is arbitrated by the
   planner on pgvector. The scope-first exact leg is the correct default;
   ANN is an accelerator for wide scopes on Postgres (with
   `hnsw.iterative_scan`) and for unscoped queries elsewhere.
5. **Push the glob scope down as a predicate, not a list** (segment/prefix
   join as grep does), so one statement covers any scope width; use the
   id-list form only for observation piping, chunked by
   `membership_budget` with client-side leg merge + Python fusion when it
   exceeds one chunk (§5).
6. **Declare per-dialect facts SQLAlchemy does not model** where vector
   config lives: storage and index dimension caps (pg 16,000 / 2,000 hnsw,
   halfvec 4,000; mssql 1,998; mysql 16,383; mariadb <16,383 by row size;
   oracle 65,535), distance-function availability (absent on mysql and
   generic), ANN-with-scope behaviour, and whether native FTS is BM25.
7. **Bump the Docker legs**: `postgres:17` → `pgvector/pgvector:pg17`
   (superset; the plain image cannot `CREATE EXTENSION vector`),
   `mariadb:11.4` → `11.8`, `mysql:8.4` → `9`, `mssql/server:2022-latest` →
   `2025-latest` with a small Dockerfile that installs `mssql-server-fts`
   and a user database for the FTS/preview legs (both refused in
   `master`), and `gvenzl/oracle-free:23-slim` → `:23` (regular) whenever
   the lexical leg is tested (slim has no Oracle Text), with
   `vector_memory_size` set at the CDB root for HNSW tests. All `23`
   tags now resolve to 26ai 23.26.x.

**Open forks the memo must decide** (named, not settled here):

- **F1 — Engine FTS vs. our own term tables for the lexical leg.** Engine
  FTS is BM25 only on SQL Server (`FREETEXTTABLE`) and SQLite; Postgres,
  MySQL/MariaDB and Oracle rank by frequency/TF-IDF/Salton. Under RRF only
  ranks matter, so engine FTS is a defensible lexical *tier*, but
  cross-engine rank consistency and the GENERIC floor argue for the
  portable `(term, chunk_id, tf)` table (brief Q2, priced by its own
  study). Both can coexist behind the leg seam.
- **F2 — Fusion in SQL vs. always in Python.** In-engine fusion moves
  ≤ `kv + kl` rows instead of two lists of `k` — a saving of one round
  trip and a few hundred rows, not of data volume. Since the Python fuser
  must exist anyway (MySQL, GENERIC, cross-mount, list-scope chunking), the
  memo should weigh one ranking code path against R1's "in the engine"
  requirement with that number in view.
- **F3 — Predicate scope vs. list scope** as the primary pushdown (§5).
- **F4 — Native vector types on SQL Server and MariaDB vs. `VARBINARY`
  everywhere except Postgres/Oracle.** Native buys server-side distance on
  both, at the cost of two custom types and MariaDB's row-size cap.
- **F5 — The recall record.** pgvector's plan choice and Oracle's
  `TARGET ACCURACY` make "approximate" a per-query fact; whether the
  backend reads the plan (`EXPLAIN` costs a round trip) or infers the tier
  from configuration (index present + no scope) is a design choice with
  honesty consequences.

---

## Sources

Executed probes and raw results (this repo):
`engine-matrix/probe_versions.py` → `results_versions.json`;
`probe_fused_pg.py`, `probe_fused_maria.py` (MariaDB + MySQL),
`probe_fused_mssql.py`, `probe_fused_oracle.py`, `probe_fused_sqlite.py` →
`results_fused_*.json`; `probe_pg_scale.py` (50k-row plans, dimension caps)
→ `results_pg_scale.json`; `probe_mssql_ann.py` → `results_mssql_ann.json`;
`probe_oracle_hnsw.py` → `results_oracle_hnsw.json`; `bench_floor_mysql.py`
→ `results_floor_mysql.json`; shared `probe_common.py`, `corpus.py`.

Reference checkouts (read-only, cited above by path): sqlalchemy
`0770f6e96` (`lib/sqlalchemy/dialects/oracle/vector.py`,
`oracle/base.py:776-1000, 1339, 1891`, `mysql/expression.py`,
`mysql/base.py:1571-1609`, `mssql/base.py:2107`,
`postgresql/base.py:2280`, `postgresql/ext.py:370-420`,
`postgresql/types.py:164, 358`); pgvector `e48241b` (`README.md`,
`src/vector.h`, `src/hnsw.h`, `src/ivfflat.h`, `src/halfvec.h`);
pgvector-python `60739df` (`pgvector/sqlalchemy/*.py`, `README.md:169-290`);
sqlite-vec `04d28bd` (`README.md`).

Vendor documentation:

- MariaDB: Vector Overview —
  https://mariadb.com/docs/server/reference/sql-structure/vectors/vector-overview;
  Optimizing Hybrid Search Query with RRF —
  https://mariadb.com/docs/server/reference/sql-structure/vectors/optimizing-hybrid-search-query-with-reciprocal-rank-fusion-rrf;
  VEC_DISTANCE_COSINE —
  https://mariadb.com/docs/server/reference/sql-functions/vector-functions/vec_distance_cosine
- MySQL 9.7 manual: Vector Functions —
  https://dev.mysql.com/doc/refman/9.5/en/vector-functions.html (page
  serves 9.7); Natural Language Full-Text Searches —
  https://dev.mysql.com/doc/refman/9.5/en/fulltext-natural-language.html
- Microsoft Learn: Vector data type —
  https://learn.microsoft.com/en-us/sql/t-sql/data-types/vector-data-type?view=sql-server-ver17;
  VECTOR_SEARCH —
  https://learn.microsoft.com/en-us/sql/t-sql/functions/vector-search-transact-sql?view=sql-server-ver17;
  Limit search results with RANK (BM25 formula) —
  https://learn.microsoft.com/en-us/sql/relational-databases/search/limit-search-results-with-rank?view=sql-server-ver17;
  Azure SQL blog, Hybrid Search and RRF re-ranking —
  https://devblogs.microsoft.com/azure-sql/enhancing-search-capabilities-in-sql-server-and-azure-sql-with-hybrid-search-and-rrf-re-ranking/
- Oracle: DBMS_HYBRID_VECTOR —
  https://docs.oracle.com/en/database/oracle/oracle-database/26/arpls/dbms_hybrid_vector1.html;
  Understand Hybrid Search —
  https://docs.oracle.com/en/database/oracle/oracle-database/26/vecse/understand-hybrid-search.html;
  CREATE HYBRID VECTOR INDEX —
  https://docs.oracle.com/en/database/oracle/oracle-database/26/vecse/create-hybrid-vector-index.html;
  Size the Vector Pool —
  https://docs.oracle.com/en/database/oracle/oracle-database/26/vecse/size-vector-pool.html;
  Oracle Text Scoring Algorithm —
  https://docs.oracle.com/en/database/oracle/oracle-database/18/ccref/oracle-text-scoring-algorithm.html
- PostgreSQL 17: Controlling Text Search (ts_rank / ts_rank_cd) —
  https://www.postgresql.org/docs/17/textsearch-controls.html
- SQLite: FTS5 Extension — https://www.sqlite.org/fts5.html
- gvenzl/oci-oracle-free image flavors —
  https://github.com/gvenzl/oci-oracle-free and
  https://raw.githubusercontent.com/gvenzl/oci-oracle-free/main/ImageDetails.md
