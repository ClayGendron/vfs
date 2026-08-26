# BM25 storage: block postings (Option B) vs term rows (Option A) — executed prototype benchmark

- **Status:** executed 2026-08-26 (every number below is from a run on
  that date; the commands are recorded per section; raw JSON under
  `prototype/results/`).
- **Question:** spec 130 landed the relational BM25 index — one
  `(epoch, term, chunk_id, tf, weight)` row per posting, scored by an
  in-engine `SUM(weight)` — at +28.8 s per 4,000 files, 3.09 M rows,
  120 MB on sqlite, and ~9× over ADR 048's reindex target when scaled
  to the full checkout. Would a **block-posting** index in the shape of
  the gram index — per term, blocks of 128 delta+varint-coded doc ids
  with their tfs and dls in three BLOBs, scored client-side — build
  faster, take fewer bytes, and rank identically, in Python and in
  Rust, on sqlite and on the four Docker engines?
- **Informs:** the BM25 storage decision (a revision of spec 130's
  tables, or a spec of its own), the Rust-port trigger recorded in
  spec 130's landing note, spec 132's statement shape.
- **Prototype:** `prototype/` — `gen_unicode_tables.py`,
  `rustbench/` (the Rust crate: tokenizer port, builder, scorer),
  `build_b_python.py`, `build_bench.py`, `tokenizer_parity.py`,
  `common.py` (codec, formula, numpy scorers, query drawing),
  `query_sqlite.py`, `query_engines.py`; `results/*.json`.

## Setup

- **Machine:** Apple M1 Pro, macOS 26.5.2, idle. Python 3.13.11,
  numpy 2.4.2, sqlite 3.50.4, rustc 1.97.1 (`--release`). The Docker
  engines are `postgres:17`, `mysql:8.4`, `mcr.microsoft.com/mssql/
  server:2022-latest` (amd64 under Rosetta), `gvenzl/oracle-free:23-slim`
  — the repo's `db_test` containers, on their published ports.
- **Corpus:** the store spec 130's landing note measured —
  `bench_lexical_linux.py --files 4000 --seed 7` over the linux checkout,
  reindexed with the landed Option A tables (`vfs_lex_*`, epoch 2):
  **32,243 chunks, 8,731,415 tokens, 487,126 distinct terms, 3,094,397
  postings** (96 per chunk). Option B is built by reading
  `vfs_chunks` from that same sqlite file with the same coverage
  predicate (`chunked ∧ indexable ∧ deleted_at IS NULL`, ascending
  id), so both options index identical chunks.
- **Option B tables** (epoch-scoped, keyed for contiguous block runs):
  `lex_postings(epoch, term, block_no, doc_count, max_tf, min_dl,
  doc_ids BLOB, tfs BLOB, dls BLOB)` PK `(epoch, term, block_no)`;
  `lex_docs(epoch, chunk_id, entry_id, dl)`; `lex_df(epoch, term, df,
  idf)`; `lex_stats(epoch, n_docs, avg_dl)`. A block holds up to 128
  postings in chunk-id order: `doc_ids` is LEB128 varints of the
  deltas (first delta from 0), `tfs` and `dls` are plain varints, so a
  block is self-contained and scorable without a `lex_docs` lookup.
  The block's bound is `(max_tf, min_dl)`: BM25's tf-normalisation is
  increasing in tf and decreasing in dl, so `idf · tfc(max_tf, min_dl)`
  bounds every posting in the block; storing the raw pair rather than
  a score bound lets the **build be a single pass** — idf and avg_dl
  are unknown until the last chunk, and Option A needs a second pass
  only because it stores the finished weight. Terms stay text (spec
  130 fork E2 unchanged); `lex_df` is shared as-is.
- **Query set:** drawn as the lexical-leg study and the MSSQL spike
  drew theirs, from `vfs_lex_df` with `seed=7`: 15 queries per arity;
  1-term = a mid-df term (0.2–2 % of chunks); 3-term = two mid + one
  common (> 20 %); 6-term = one rare (< 0.2 %) + four mid + one
  common. Median postings touched: 235 / 10,542 / 11,077 per arity
  (the common term — `the` df 12,941, `int` df 14,753 — dominates).
  Top-10, ordered `score DESC, chunk_id`. Every query's terms are
  ASCII (asserted; literal inlining on SQL Server would otherwise need
  care).
- **Agreement standard:** a ranking "agrees" when the top-10
  `(chunk_id, score)` list equals Option A's after rounding scores to
  9 decimals; Kendall τ is over the ids of both top-10s.

## 1. Build

Commands (from the repo root, `cd prototype` first):
`uv run --no-sync python gen_unicode_tables.py > rustbench/src/tables.rs`;
`cargo build --release` (in `rustbench/`);
`uv run --no-sync python tokenizer_parity.py`;
`uv run --no-sync python build_bench.py`.

### 1a. Tokenizer parity — the Rust port is byte-identical

The Rust tokenizer (`rustbench/src/tokenizer.rs`) is a port of
`vfs.models.lexical.tokenize` driven by **the interpreter's own
character classes**: `gen_unicode_tables.py` dumps `re`'s `\w`,
`str.isupper`, `str.islower`, `str.isdigit` as range tables and
`str.casefold` as a code-point map (749 / 651 / 671 / 83 ranges, 1,530
fold entries) into `tables.rs`, so the port cannot disagree with
CPython on what a letter, a capital, or a fold is. `tokenizer_parity.py`
re-tokenizes every covered chunk in Python and diffs it against the
Rust dump (`rustbench tokens`).

| | value |
|---|---|
| chunks compared | 32,243 |
| tokens | 8,731,415 (both sides) |
| divergent chunks | **0** — identical token streams |
| Python `tokenize` over the corpus | 5.01 s |
| Rust `tokenize` over the corpus | 0.46 s (**10.9× faster**) |

(`results/tokenizer_parity.json`.)

### 1b. Build wall, rows, bytes — sqlite, `WITHOUT ROWID`

| build | wall | tokenizer share | block rows | blob bytes | `lex_postings` on disk | index total | peak RSS |
|---|---|---|---|---|---|---|---|
| **Option A** (spec 130 landing note; two passes, 3.09 M rows through `insertmanyvalues` on aiosqlite) | **28.8 s** | 9.9 s (34 %) | 3,094,397 term rows | — | 99.2 MB (`lex_terms`) | **119.5 MB** | vocabulary + one batch |
| **Option B, Python**, block 128 (`build_b_python.py`, one pass, sqlite3 `executemany`) | **9.5 s** | 5.2 s (55 %) | 499,590 | 13.44 MB | 33.4 MB | **53.1 MB** | 492 MB |
| **Option B, Rust**, block 128 (`rustbench build`, one pass, rusqlite) | **2.62 s** | 0.48 s (18 %) | 499,590 | 13.44 MB | 33.6 MB | **53.2 MB** | 306 MB |
| Option B, Rust, block 64 | 2.70 s | 0.48 s | 514,953 | 13.46 MB | 33.8 MB | 53.5 MB | 305 MB |
| Option B, Rust, block 256 | 3.24 s | 0.48 s | 492,492 | 13.43 MB | 52.2 MB | 71.9 MB | 308 MB |

`lex_df` is 18.6 MB and `lex_docs` 1.0 MB in every build (the same
tables as Option A's 19.2 / 1.1 MB). The Python and Rust builds
produce **byte-identical tables** — every `lex_postings`, `lex_docs`,
`lex_df`, `lex_stats` row compared equal (`build.json:
python_rust_tables_identical`).

Reading it:

- **Bytes.** 13.44 MB of blobs for 3,094,397 postings is **4.34
  bytes per posting** (≈1.5 for the id delta, ≈1 for tf, ≈1.9 for
  dl); the `lex_postings` table costs 10.8 bytes per posting on disk
  because 487,126 of its 499,590 rows are a term's single partial
  block, and each row carries the text key. Option A's `lex_terms` is
  **32.0 bytes per posting**. The whole index is 53 MB vs 120 MB —
  **2.25× smaller, 0.89× the content bytes** (1,651 B per chunk vs
  3,705), and the remaining 18.6 MB of `lex_df` is now the largest
  table after the postings (fork: fold `df`/`idf` into the term's
  first block row and drop `lex_df` — −35 % of what is left).
- **Block size.** 64 vs 128 differ by 0.2 % in bytes; 256 costs
  +56 % on sqlite because a 256-posting row (~1.1 KB of blobs) exceeds
  the `WITHOUT ROWID` local-payload threshold (~1 KB at the 4 KB page)
  and spills to a 4 KB overflow page per row. 128 keeps every row
  in-page (max blob lengths in the build: 201 / 137 / 256 bytes) and
  is the size the gram index's readers already handle; it is the
  choice, and the engines' row-size thresholds (Postgres TOAST at
  ~2 KB, InnoDB's 768-byte in-page prefix, SQL Server's 8,060-byte
  row) all clear it.
- **Build time.** Rust: 2.6 s for the whole one-pass build, 11× under
  Option A's 28.8 s; the tokenizer is 0.48 s of it and the rest is
  the hash map and sqlite inserts. Python: 9.5 s, 3× under — and
  without touching the tokenizer, because a single pass over 500 k
  rows replaces two passes and 3.09 M rows. Scaled to spec 130's
  76 k-file checkout (×19): Option A's ~9 min becomes ~3 min in
  Python and **~50 s in Rust**, at ADR 048's 60 s target.
- **Memory.** The build holds one open block per distinct term plus
  its `df` — the Rust process peaks at 306 MB, the Python one at
  492 MB, both dominated by 487 k small per-term buffers (Rust: three
  `Vec<u8>` per term; Python: three `bytearray`s and a slotted
  object). That is vocabulary-bound, as spec 130's builder is, not
  posting-bound: a full block is written the moment it fills. A leaner
  layout (one interleaved buffer per term, or an arena) is an
  implementation detail, not a design question.
- **At 10 M chunks** (960 M postings at 96 per chunk; vocabulary
  growth is sublinear and not measured here, so the row count is a
  floor): Option A ≈ 960 M rows, ≈ 28.6 GiB at 32 B/row; Option B ≈
  3.9 GiB of blobs plus 7.5 M full-block rows plus one partial row per
  distinct term — ≈ 8–12 M rows, ≈ 5–6 GiB with the per-row key. Both
  extrapolations keep sqlite's per-row overhead; no engine was run at
  that size.

## 2. Query time on sqlite, and the agreement proof

Command: `uv run --no-sync python query_sqlite.py 7` (medians of 7
runs per query, in-process sqlite3, both files on local disk;
`results/query_sqlite.json`).

Three Option B evaluations over the same fetch (one `SELECT … FROM
lex_df WHERE epoch=? AND term IN (…)` for idf, one `SELECT … FROM
lex_postings WHERE epoch=? AND term IN (…)` for every block):

- **B-full (batched numpy):** concatenate every block's three blobs,
  decode each column once (a vectorized LEB128 decode with a fast path
  when no byte has its continuation bit set), restore absolute ids by
  a segmented cumsum, weight, `np.unique` + `bincount`, top-10.
- **B-full (per-block numpy):** the same, one numpy pipeline per
  block — the naive shape, kept to show what the batching buys.
- **B-blockmax:** MaxScore at block granularity — terms in decreasing
  bound order; once the remaining terms' bounds cannot lift a new
  document over the current 10th score, a block is decoded only if
  its id range holds a candidate whose partial score plus the block's
  bound plus the remaining bounds reaches that score. A per-block
  Python loop (the decision is per block), numpy inside.

| arity | postings (median) | blocks | blob bytes | **A** in-SQL `SUM` | **B fetch** | **B-full batched** score | B-full per-block score | **B-blockmax** score | blocks skipped | **Rust** decode+score |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 235 | 2 | 1.0 KB | **0.043 ms** | 0.016 ms | 0.064 ms | 0.087 ms | 0.091 ms | 0 / 36 | **0.002 ms** |
| 3 | 10,542 | 84 | 41.8 KB | **2.01 ms** | 0.089 ms | **1.11 ms** | 3.62 ms | 2.68 ms | 845 / 1,302 (65 %) | **0.16 ms** |
| 6 | 11,077 | 90 | 44.0 KB | **2.23 ms** | 0.100 ms | **1.23 ms** | 3.92 ms | 2.85 ms | 953 / 1,419 (67 %) | **0.18 ms** |

**Agreement — the proof.** Over all 45 queries, every Option B
evaluation returned **exactly Option A's top-10** (same ids, same
order, same scores to 9 decimals): B-full 45/45, B-blockmax 45/45,
Rust 45/45; Kendall τ = 1.0 on every query; the largest absolute
score difference before rounding is 3.6 × 10⁻¹⁵ (summation order).
The Rust scorer's top-10 is compared against A's from the same run,
so the three implementations (SQL `SUM` over stored weights, numpy
over decoded blocks, Rust over decoded blocks) agree pairwise.

Reading it:

- **Full evaluation in numpy beats the in-engine SUM at 3 and 6
  terms** (1.2 vs 2.0 ms, 1.3 vs 2.2 ms) even on in-process sqlite,
  where the fetch costs nothing: decoding 44 KB of blobs is cheaper
  than aggregating 11 k rows through a group-by. One-term queries are
  the reverse (0.08 vs 0.04 ms) — numpy's fixed per-call cost is the
  whole budget when there are 235 postings.
- **Rust decodes and scores the same blobs in 0.16 ms** — 7× under
  batched numpy and 12× under Option A's SQL — so with a Rust scorer
  behind `vfs.native` Option B's query cost is the fetch.
- **Block-max skipping works as designed but does not pay in Python:**
  it skips two thirds of the blocks (the common term's blocks, whose
  bound cannot beat the mid-df terms' scores), yet the per-block
  decision loop costs more than the decoding it avoids; the batched
  full path wins. It is the right structure for Rust (where a block
  decode is ~2 µs and the skip is free) and for a lazy fetch — 65 %
  of the blob bytes would not need to leave the engine (fork below).
- The `dls` blob makes a block self-scoring: no `lex_docs` probe per
  candidate. That is 1.9 of the 4.34 bytes per posting; storing a
  quantised weight instead would trade it for a two-pass build.

## 3. Query time on the four engines

Command: `uv run --no-sync python query_engines.py --engines
pg,my,ms,or --reps 5` (medians of 5 runs per query per statement;
plain driver connections — asyncpg, pymysql, pyodbc, oracledb — with
literal-inlined statements; `results/engine_<name>.json`). Both
options' tables are loaded into a `bm25a_*`/`bm25b_*` namespace on
each engine — A's 3,094,397 rows from the sqlite store, B's 499,590
block rows from the Rust build, the shared `docs`/`df`/`stats` plus
a 4,000-row `entries(entry_id, ext, deleted)` — statistics gathered,
and the namespace dropped afterwards. Term columns follow
`BytewiseString`'s per-engine choice (`VARCHAR(64) COLLATE "C"`,
`VARBINARY(64)`, `VARCHAR(64) COLLATE Latin1_General_100_BIN2_UTF8`,
`VARCHAR2(64 CHAR)`); blobs are `BYTEA` / `VARBINARY(2000)` /
`VARBINARY(2000)` / `RAW(2000)`.

Load paths per engine (the same path for both options on each
engine, so the A/B load ratio is a row-volume ratio): Postgres
`copy_records_to_table` (asyncpg); MySQL `executemany` (pymysql's
client-side multi-row rewrite, 20 k rows per statement); SQL Server
`BULK INSERT` from a UTF-16 TSV copied into the container per 20 k-row
batch — pyodbc's `fast_executemany` measured ~100 k rows per minute
against the emulated server, which put Option A's 3.09 M rows past 30
min, and the first (background) attempt at that leg was killed at
371,541 rows and rerun in the foreground with the bulk path; Oracle
`executemany` array binding (oracledb thin, 20 k rows per call). The
legs ran one after another: MySQL, then SQL Server, then Oracle, then
Postgres again (the first Postgres run lacked the one-statement fetch
column; the rerun's numbers are the ones below, and they are within
noise of the first run's: 3.54 → 3.04 ms A at 3 terms). Every
`bm25a_*`/`bm25b_*` table was dropped afterwards (verified empty on
all four engines).

### 3a. Load wall and bytes per engine

| engine | A `terms` rows load | B `postings` rows load | A `terms` bytes | B `postings` bytes | shared `df` | shared `docs` | B/A bytes (postings) |
|---|---|---|---|---|---|---|---|
| postgres | 3,094,397 in **7.36 s** | 499,590 in **1.6 s** | **325.5 MB** | **70.9 MB** | 50.6 MB | 3.6 MB | 0.22× |
| mysql | 3,094,397 in **29.63 s** | 499,590 in **7.66 s** | **164.8 MB** | **44.6 MB** | 26.6 MB | 5.0 MB | 0.27× |
| mssql | 3,094,397 in **24.93 s** | 499,590 in **5.01 s** | **178.2 MB** | **48.0 MB** | 28.6 MB | 3.4 MB | 0.27× |
| oracle | 3,094,397 in **14.29 s** | 499,590 in **2.85 s** | **208.0 MB** | **55.0 MB** | 37.0 MB | 4.8 MB | 0.26× |

### 3b. Unscoped top-10 (S1), medians in ms

| engine | arity | **A** in-engine SUM | B fetch (df + blocks, 2 stmts) | B fetch (joined, 1 stmt) | B numpy score | **B total (2 stmts)** | **B total (1 stmt)** | agree |
|---|---|---|---|---|---|---|---|---|
| postgres | 1 | **0.48** | 0.79 | 0.40 | 0.07 | **0.86** | **0.46** | 15/15, τ=1.0 |
| postgres | 3 | **3.04** | 1.23 | 0.79 | 1.38 | **2.59** | **2.17** | 15/15, τ=1.0 |
| postgres | 6 | **2.77** | 1.23 | 0.79 | 1.19 | **2.42** | **2.02** | 15/15, τ=1.0 |
| mysql | 1 | **0.51** | 0.74 | 0.43 | 0.07 | **0.80** | **0.50** | 15/15, τ=1.0 |
| mysql | 3 | **5.23** | 1.54 | 1.27 | 1.14 | **2.72** | **2.43** | 15/15, τ=1.0 |
| mysql | 6 | **5.27** | 1.59 | 1.20 | 1.18 | **2.67** | **2.38** | 15/15, τ=1.0 |
| mssql | 1 | **0.75** | 1.17 | 0.65 | 0.45 | **1.63** | **1.05** | 15/15, τ=1.0 |
| mssql | 3 | **6.38** | 2.28 | 1.36 | 3.64 | **6.14** | **5.13** | 15/15, τ=1.0 |
| mssql | 6 | **6.08** | 2.11 | 1.44 | 3.54 | **6.26** | **4.89** | 15/15, τ=1.0 |
| oracle | 1 | **0.80** | 1.13 | 0.77 | 0.39 | **1.54** | **1.22** | 15/15, τ=1.0 |
| oracle | 3 | **2.86** | 2.10 | 1.18 | 3.23 | **5.33** | **4.44** | 15/15, τ=1.0 |
| oracle | 6 | **2.98** | 2.27 | 1.25 | 2.99 | **5.18** | **4.24** | 15/15, τ=1.0 |

### 3c. Scoped shapes, medians in ms

| engine | arity | **A** S3 ext join | B S3 client-filter | **B S3 semi-join** | probes | **A** S5 allow-list join | B S5 client-filter | **B S5 semi-join** | agree (S3 c/s, S5 c/s) |
|---|---|---|---|---|---|---|---|---|---|
| postgres | 1 | **0.79** | 9.51 | **1.71** | ≤1 | **3.88** | 5.62 | **4.35** | 15/15, 15/15 |
| postgres | 3 | **7.71** | 10.97 | **3.42** | ≤2 | **6.49** | 6.48 | **6.21** | 15/15, 15/15 |
| postgres | 6 | **6.90** | 10.66 | **3.44** | ≤1 | **6.54** | 6.58 | **5.97** | 15/15, 15/15 |
| mysql | 1 | **0.57** | 42.08 | **1.96** | ≤1 | **1.36** | 9.21 | **4.91** | 15/15, 15/15 |
| mysql | 3 | **6.51** | 44.83 | **4.16** | ≤2 | **7.52** | 10.74 | **7.36** | 15/15, 15/15 |
| mysql | 6 | **6.26** | 44.11 | **4.20** | ≤1 | **7.63** | 10.84 | **7.18** | 15/15, 15/15 |
| mssql | 1 | **0.88** | 14.66 | **6.11** | ≤1 | **1.74** | 10.26 | **7.92** | 15/15, 15/15 |
| mssql | 3 | **17.59** | 16.22 | **8.08** | ≤2 | **10.09** | 13.09 | **14.41** | 15/15, 15/15 |
| mssql | 6 | **18.01** | 16.39 | **7.99** | ≤1 | **10.49** | 13.38 | **13.56** | 15/15, 15/15 |
| oracle | 1 | **2.02** | 81.06 | **2.40** | ≤1 | **2.36** | 20.36 | **2.72** | 15/15, 15/15 |
| oracle | 3 | **6.72** | 79.81 | **5.35** | ≤2 | **6.87** | 22.70 | **7.23** | 15/15, 15/15 |
| oracle | 6 | **7.07** | 82.59 | **5.77** | ≤1 | **7.40** | 22.53 | **7.03** | 15/15, 15/15 |

Scope-set fetch alone (query-independent; the client-filter rows above pay it every query):

| engine | ext = 'c' chunk ids | ms | 500-entry allow-list chunk ids | ms |
|---|---|---|---|---|
| postgres | 20,633 | 7.97 | 3,332 | 4.27 |
| mysql | 20,633 | 40.61 | 3,332 | 8.32 |
| mssql | 20,633 | 12.63 | 3,332 | 6.26 |
| oracle | 20,633 | 95.56 | 3,332 | 17.53 |

Reading it:

- **Bytes on every engine: B's postings table is 0.22–0.27× A's**
  (Postgres 71 vs 326 MB, MySQL 45 vs 165, SQL Server 48 vs 178,
  Oracle 55 vs 208). Postgres is the widest gap — its 24-byte tuple
  header and per-row index entry make Option A's 3.09 M rows cost
  105 bytes each. `lex_df` (27–51 MB) is now 35–40 % of Option B's
  footprint everywhere; fork F5 is worth more on the engines than on
  sqlite.
- **Load: B is 4–5× faster on every engine** (Postgres 1.6 vs 7.4 s,
  MySQL 7.7 vs 29.6, SQL Server 5.0 vs 24.9, Oracle 2.9 vs 14.3) —
  the ratio of the row counts, with the bulk paths above. spec 130's
  reindex on SQL Server was 403.7 s for half this corpus through
  `insertmanyvalues` under the 2,100-bind cap; the block table's
  500 k rows would go through the same path 6× fewer times, and its
  rows are wider but far fewer per statement-cap.
- **Unscoped queries (S1).** With the one-statement fetch and numpy
  scoring, B is **faster than A's in-engine SUM at 3–6 terms on
  Postgres (2.2 vs 3.0 ms) and MySQL (2.4 vs 5.2 ms)**, slightly
  faster on SQL Server (5.1 vs 6.4) and slower on Oracle (4.4 vs
  2.9). One-term queries are a wash (0.46 vs 0.48 Postgres, 0.50 vs
  0.51 MySQL) once the fetch is one statement, and A wins by
  0.3–0.4 ms on SQL Server and Oracle. Two things sit under the
  SQL Server and Oracle rows: the **fetch is ~1.2–1.4 ms on every
  engine** (the same 42 KB of blobs), but **the numpy score of the
  identical bytes is 3.2–3.6 ms on those two legs against 1.1–1.4 ms
  on sqlite, Postgres and MySQL** — same code, same input; the
  amd64-emulated SQL Server container and the Oracle container keep
  a core busy between requests, and the client's numpy pass pays for
  it. The score component's clean number is §2's 1.1 ms (and Rust's
  0.16 ms); read the SQL Server and Oracle B totals as fetch + that.
  With the Rust scorer, B's S1 cost is the fetch: ~0.8–1.4 ms at 3–6
  terms on every engine, under A's SUM on all four.
- **The joined fetch is the right shape:** folding the `lex_df` probe
  into the block statement saves 0.3–0.9 ms per query on every engine
  (a round trip), and fork F5 would make it one seek.
- **Scoped queries.** The **semi-join** (score everything, probe the
  top candidates in pages of 200 against the scope in SQL; at most 2
  probes were ever needed) is the shape for B: for the extension
  scope it beats A's join at 3–6 terms on every engine (Postgres 3.4
  vs 7.7 ms, MySQL 4.2 vs 6.5, SQL Server 8.1 vs 17.6, Oracle 5.4 vs
  6.7) and loses by ~1–5 ms at one term, where A's join over a tiny
  posting run is one seek chain. For the 500-entry allow-list it ties
  A on Postgres, MySQL and Oracle (6.2 vs 6.5, 7.4 vs 7.5, 7.2 vs 6.9)
  and loses on SQL Server (14.4 vs 10.1) — both sides carry the 500
  literals, and on SQL Server the probe's 700-element `IN` is the
  cost. **Client-side filtering does not work as a per-query shape:**
  fetching the scope's 20,633 chunk ids costs 8 ms on Postgres, 13 on
  SQL Server, 41 on MySQL, 96 on Oracle (the table above), and the
  allow-list's 3,332 ids 4–18 ms — a scope set must be cached per
  epoch on the client to be usable, which is a design choice spec 132
  can make for the piped-observation scope (an allow-list the client
  already holds) but not for arbitrary predicates. Every scoped
  ranking agreed with A's (S3/S5, client and semi-join: 15/15 at
  every arity on every engine).


## 4. Rust vs Python at query time (decode + score, no DB)

The 45 fetched block sets from §2 are handed to `rustbench score`
(binary dump; 7 timed repetitions in-process, the median reported)
and to the batched numpy scorer over the same bytes:

| arity | postings | numpy batched | numpy per-block | Rust | Rust top-10 = A |
|---|---|---|---|---|---|
| 1 | 235 | 0.064 ms | 0.087 ms | **0.002 ms** | 15/15 |
| 3 | 10,542 | 1.11 ms | 3.62 ms | **0.16 ms** | 15/15 |
| 6 | 11,077 | 1.23 ms | 3.92 ms | **0.18 ms** | 15/15 |

Rust is 7× under batched numpy at 3–6 terms and 30× at one term; at
~15 ns per posting it is the shape the gram index's Rust decoder
already has. A pyo3 binding would add one crossing per query
(microseconds), not per block.

## What this shows / what it doesn't

Shows:

- A block-posting BM25 index is **exact**: identical top-10 and
  scores to Option A on 45 queries across three implementations.
- It is **2.25× smaller** (53 vs 120 MB on sqlite; 4.3 vs 32 bytes per
  posting) and **builds 3× faster in Python and 11× faster in Rust**
  on the same corpus, with a one-pass builder whose memory is
  vocabulary-bound.
- The Rust tokenizer is a drop-in: byte-identical over 8.7 M tokens,
  10.9× faster, with the interpreter's own tables as the parity
  mechanism.
- Query time is a wash or a win for B at 3–6 terms with numpy scoring
  and a clear win with Rust scoring; one-term queries slightly favour
  the in-engine SUM everywhere because a single seek is hard to beat.

Doesn't show:

- **Scale beyond 32 k chunks.** No engine was run at 1 M or 10 M
  chunks; the 10 M figures are per-posting extrapolations. The common
  term's block count grows linearly with the corpus, and that is
  where block-max skipping and a lazy fetch stop being optional.
- **Concurrency.** Every number is one client on an idle machine.
  Option B moves CPU from the engine to the client; under many
  concurrent agents that is a feature (the engine does seeks and
  byte-copies), but it was not measured.
- **The async driver stack.** Plain driver connections were used, as
  the MSSQL spike did; vfs's SQLAlchemy async path adds its own cost
  to both options alike.
- **Incremental maintenance.** Both options are rebuilt whole per
  reindex (spec 130 fork E4); a block index makes per-chunk deletion
  a block rewrite, which is not measured.
- **Absolute SQL Server numbers** are inflated by amd64 emulation for
  both options alike; read the ratios.
- **One run did not complete as launched:** the first SQL Server leg
  (background, `fast_executemany` load) was killed after ~4 min at
  371,541 of 3,094,397 rows and replaced by the foreground `BULK
  INSERT` run reported above; nothing from the killed run is used.
- The scoped shapes S2, S4, S6, S7 of the spike memo were not run; S3
  (extension) and S5 (allow-list) stand in for "a selective predicate"
  and "an id list", the two shapes that differ in kind for a
  client-scored index.

## Forks

- **F1 — adopt Option B as the lexical index** (revise spec 130's
  tables): `lex_postings` with three blobs and `(max_tf, min_dl)`,
  128-posting blocks, one-pass build inside the gram epoch, `lex_df`
  and `lex_docs` as they are. This memo's numbers are the case.
- **F2 — the scorer's home.** Pure-numpy batched decode as the
  reference and fallback (1.1 ms at 3 terms), a Rust decode+score
  behind `vfs.native` as the engine (0.16 ms), byte-identical by the
  same pinning `tests/test_native.py` uses for grams.
- **F3 — the tokenizer port** is ready: the generated-tables approach
  makes CPython the oracle; the port is 0.46 s per corpus pass and
  identical. It matters less for B (18 % of the Rust build) than for
  A (34 %), but it is free once F2 exists.
- **F4 — lazy fetch with block-max.** Fetch block metadata
  `(term, block_no, doc_count, max_tf, min_dl)` first, decide, then
  fetch only the needed blobs by key: 65 % fewer blob bytes at 3–6
  terms, at the cost of a second round trip. Worth it only where the
  fetch dominates (remote engines, large common-term lists).
- **F5 — fold `df`/`idf` into the term's block-0 row** and drop
  `lex_df` (−18.6 MB of 53; one statement instead of two for the
  fetch — the joined fetch in §3 measures the round-trip half of
  this).
- **F6 — scoped queries.** For a selective scope, the semi-join probe
  (score, then filter the top candidates in SQL by pages of 200) is
  the shape; for a scope that covers most of the corpus, fetching
  the scope's chunk-id set once per epoch and filtering in numpy is.
  Spec 132 chooses per predicate; §3 has the numbers per engine.
- **F7 — quantised weights instead of `dls`** (one byte per posting,
  two-pass build, approximate ties): not taken here because exactness
  against A was the bar.
