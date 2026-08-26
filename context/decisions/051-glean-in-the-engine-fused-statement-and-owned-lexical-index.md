# 051. glean in the Engine: One Fused Statement, an Owned Lexical Index, Exact-First Vector Tiers, Predicate Scope

- **Status:** accepted 2026-08-26 — the storage half of the glean
  decision set, resolved by Clay in session (the R1–R5 review of the
  2026-08-26 research leg). Companions: ADR 052 (ranking and the
  cross-mount merge), ADR 053 (ranking signals and the ranker API), ADR
  054 (the embedding provider). ADR 007's verb surface is untouched;
  this ADR decides what the database backend's `glean` *is* beneath it.
- **Date:** 2026-08-26
- **Deciders:** Clay Gendron
- **Decided by:** human
- **Context source:** `context/research/2026-08-26-glean-in-the-engine.md`
  and its studies under `context/research/studies/2026-08-26-glean/`
  (`engine-matrix.md`, `lexical-leg.md`, `unconstrained-design.md`,
  `landscape.md`).

## Context

ADR 007 pinned `glean(query, *, limit, paths, …)` as one fused verb with
no strategy selector and no backend has implemented `SupportsGlean`.
The reindex pipeline mints chunk rows with an `embedding` column that
nothing fills; the gram index nominates exact matches for grep and
carries no term frequencies; there is no lexical *ranking* index of any
kind. Clay's requirement: fusion of vector similarity and BM25-style
lexical ranking pushed down to the database as one statement per mount,
with glob scoping pushed down with it. Production runs on Postgres,
MariaDB, MySQL, SQL Server, Oracle and SQLite; 10,000-file batches are a
supported contract; unknown dialects are served at a conservative floor,
never refused.

The research leg executed every engine claim on running containers
(pgvector 0.8.6 on Postgres 17, MariaDB 11.8.9, MySQL 9.7.2 community,
SQL Server 2025 CU8 with full-text installed, Oracle 26ai Free, SQLite
3.50.4 + FTS5 + sqlite-vec) and built and timed the candidate lexical
index on real corpora split by `Chunk.split_batch`.

## Options considered

- **The fused statement**: hand-written CTE skeleton compiled by
  SQLAlchemy Core (chosen) vs an engine hybrid primitive (Oracle's
  `DBMS_HYBRID_VECTOR` — it embeds a text column with an in-database ONNX
  model and cannot use a Storage-owned provider's vectors: `DRG-51504`,
  `ORA-02327`; nothing comparable exists elsewhere) vs always fusing in
  Python (one code path, but a second round trip and the loss of
  in-engine `LIMIT` on entries).
- **The lexical leg**: each engine's own full-text ranking (BM25 only on
  SQL Server `FREETEXTTABLE` and FTS5; `ts_rank_cd` has no IDF; InnoDB is
  TF·IDF² with a 3-char token floor; Oracle `SCORE` is Salton-style and
  drifts with inserts; SQL Server's is asynchronously populated and
  refused in `master`; every engine owns its own tokenizer) vs a
  portable term table of our own scored by `SUM(weight) … GROUP BY
  chunk_id` (chosen; a published, reproduced method — Kamphuis et al.
  ECIR 2020 ran eight BM25 variants as SQL over term tables and found no
  significant difference between any pair).
- **The vector leg's tiers**: native ANN wherever an index exists vs
  scope-first exact with ANN as an unscoped accelerator (chosen) vs the
  July floor's lossy narrowing (sign-bit prefilter, plain-SQL IVF —
  unbuilt; Hamming recall@50 measured 0.40 at 100k on structureless
  vectors).
- **Scope pushdown**: an id allow-list inside each leg vs a predicate
  (segments join / path-prefix range, ADR 040's shape) (chosen) vs
  post-filtering after fusion (rejected: the scope must bound each leg's
  global rank, and a post-filter defeats `LIMIT n` on entries).
- **Freshness between a write and the next reindex**: serve the stale
  chunk terms silently vs exclude the dirty set with no overlay (blind to
  the file the agent just wrote) vs a budgeted live-text overlay scored
  with the epoch's statistics (chosen) vs a write-time term buffer (a
  tokenizer on the ETL write path — a future sub-fork, not now).
- **Portable vector column**: JSON text (today) vs packed little-endian
  float32 in `LargeBinary` (chosen: 14× faster and 5× smaller at 50k on
  the floor; ~1,200× faster to parse).

## Decision

1. **One fused statement, built with SQLAlchemy Core, runs on Postgres,
   MariaDB, SQL Server, Oracle and SQLite** — a vector CTE and a lexical
   CTE each ranked above its own `LIMIT`ed leg, the scope predicate
   inside each leg, `UNION ALL` + `GROUP BY` fusion (never `FULL OUTER
   JOIN`, which MariaDB and MySQL lack), per-entry aggregation inside
   each leg (ADR 052), `ORDER BY score DESC, entry_id` as the stable
   total order, `LIMIT n` on entries. Only the three leg expressions and
   the row-limit spelling vary per dialect. Verified to return
   byte-identical rankings on all five engines; the conformance suite
   pins that.
2. **MySQL community and `GENERIC` are the client floor**: the
   statement carries the lexical leg; the vector leg is a scoped exact
   scan scored in numpy in membership-budget batches; fusion runs in
   Python through the same `Fusion.fuse` the cross-mount merge uses.
   MySQL's native `VECTOR` type is never used (no distance function, no
   index, pymysql cannot decode the wire type) — the column is packed
   float32.
3. **The lexical leg is ours**: epoch-scoped tables `lex_docs(epoch,
   chunk_id, entry_id, dl)`, `lex_terms(epoch, term, chunk_id, tf,
   weight)` keyed `(epoch, term, chunk_id)`, `lex_df(epoch, term, df,
   idf)`, `lex_stats(epoch, n_docs, avg_dl)`; `weight` precomputed as
   Lucene-accurate BM25 (non-negative IDF, exact lengths, `(k1+1)`
   kept), k1 = 1.2, b = 0.75, both in the epoch's `options_hash`. Built
   in `build_epoch`'s content scan, published by the existing `encoded`
   flips and pointer CAS, reclaimed with the epochs, rebuilt whole (no
   incremental maintenance: 97 s per 1,000 entries measured vs ~4 s to
   rebuild the corpus). `lex_df` also answers the per-term `(df, N,
   avgdl)` export ADR 052 requires of every `SupportsGlean` backend. No
   engine full-text index, column or DDL is created on any dialect.
4. **One code-aware tokenizer** beside `code_grams.py`, sharing
   `fold_content`: split on non-word runs, then on `_` and case change,
   emitting the whole folded identifier *and* its parts; drop
   one-character parts; keep digit-led tokens whole; cap term length at
   64 bytes; **no stemming, no stop list** — IDF does the stop-word job
   continuously; a df ceiling on query terms bounds latency and drops
   flooding terms with a warning record. Pure-Python reference now; the
   Rust engine port behind `vfs.native` when the build's tokenizer share
   is measured to matter.
5. **Vector tiers, exact first**: native distance where the engine has
   one (Postgres, MariaDB, SQL Server, Oracle, SQLite); ANN only where
   the planner will actually use it — unscoped queries on MariaDB and
   Oracle (a scope predicate drops their vector index to an exact scan),
   Postgres with `hnsw.iterative_scan` where the extension is 0.8+; SQL
   Server 2025's DiskANN is not shipped (the index makes the table
   read-only) and its post-filtering `VECTOR_SEARCH` is never used for a
   scoped call. Every answer records which tier served each leg.
6. **Scope is a predicate**: `glean(paths=…)` takes the same globs `grep`
   does — no new parameter — compiled as the segments join / path-prefix
   range inside every leg, so one statement covers any scope width with
   zero id binds. The id-list form exists only for piped observations,
   spelled as a **semi-join subquery** (never a JOIN — 0.2–0.35 ms vs
   0.6–680 ms planner-dependent), chunked under `membership_budget` with
   a client-side leg merge when it exceeds one chunk; the PK-probe
   spelling is a candidate narrow-scope rung to be confirmed on the
   Docker legs before it is pinned.
7. **Freshness**: the lexical index rides the gram epoch's `encoded`
   partition — `encoded=True` implies the entry's terms are in the
   current lexical epoch, and the leg joins `encoded`, `deleted_at IS
   NULL` and `user_id` scoping — while a **budgeted live-text overlay**
   scores the `NOT encoded` set client-side with the epoch's `idf` and
   `avg_dl` (~1.8 ms per dirty entry measured), merged into the lexical
   leg before fusion, bounded by grep's candidate budget and deadline.
   One warning record names scanned / unconsulted / lexical-only counts
   (those entries also have `embedding IS NULL`).
8. **Declared dialect facts**, per the profile doctrine: distance-function
   availability (`none | exact | ann`; Postgres only after a first-touch
   probe finds the extension), dimension caps (pgvector 2,000 for HNSW /
   16,000 storage, `halfvec` 4,000; SQL Server 1,998; MySQL 16,383;
   MariaDB below 16,383 by row size; Oracle 65,535), and ANN-with-scope
   behaviour. A space over the cap is stored but refused for the native
   tier with a classified first-touch error.
9. **The Docker legs bump** to `pgvector/pgvector:pg17`, `mariadb:11.8`,
   `mysql:9`, `mssql/server:2025-latest` plus an in-image
   `mssql-server-fts` install and a user database, and the regular
   `gvenzl/oracle-free:23` image where Oracle Text matters, with
   `vector_memory_size` set at the CDB root for HNSW tests.

## Consequences

- **Easier:** the same ranking on every engine — the conformance suite
  pins an ordered top-10 per golden query across all six dialects;
  cross-mount merge stays honest because every mount ranks by the same
  BM25; scope never leaves the engine; unknown dialects get the full
  lexical leg and an exact vector floor with recall 1.0.
- **Harder:** the lexical index costs ~2.1–2.8× the content bytes
  (measured 41.9 MB for 19.6 MB of source at 11.6k chunks) — the price
  of ranking rather than nominating; a full rebuild per reindex; two
  small `UserDefinedType`s (SQL Server, MariaDB) and a distance-expression
  factory to maintain; a CJK tokenisation question left open (codepoint
  bigrams vs vector-only).
- **Committed to:** no engine FTS anywhere; packed float32 as the
  portable vector column; ANN as an opt-in, unscoped accelerator, never
  a correctness dependency; `signals` and `lex_df` joins as the only
  additions the fused statement makes beyond its two legs.

Evidence: `engine-matrix.md` (five engines, one statement, identical
top-5; the MySQL floor benchmark; the ANN-with-scope plans; DiskANN's
read-only table; `DBMS_HYBRID_VECTOR`'s ONNX requirement);
`lexical-leg.md` (BM25-in-SQL fidelity τ = 1.0 against bm25s; build
and latency tables at 2,690 / 4,909 / 11,608 chunks; the scope-join
diagnosis; incremental maintenance at 97 s per 1,000 entries; the
overlay cost); `unconstrained-design.md` §12 (SQL-side scoring 1.3–9.5
ms vs 2.8–21 ms in Python on 3.3M postings); `landscape.md` §7 (the
vendor record).
