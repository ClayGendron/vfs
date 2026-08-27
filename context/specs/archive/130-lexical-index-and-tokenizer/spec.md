# 130 — the lexical index: block postings per term, built and scored by the Rust engine, under the gram epoch

- **Status:** **landed 2026-08-26** (second landing, under ADR 055 as
  corrected by the staff review; the first landing a351e7b is recorded
  under *History*). Slices A–C green: `scripts/ci.sh 3.13` under both
  engines, `cargo test -p vfs-core`, 100 % coverage; the landing note
  and the one criterion missed (build wall at full linux scale) are
  under *History*. First of the glean arc (130 → 138); spec 132 builds
  the query path on it. No verb changes here: this spec builds,
  publishes and *scores* the index; spec 132 makes it a verb.
- **Born from:** ADR 055 (all pins, as corrected by the staff review
  validated in `studies/2026-08-26-bm25-storage/review-validation.md`);
  ADR 051 pins 4, 7 (tokenizer, freshness) as amended; memo
  `../../../research/2026-08-26-bm25-storage-design.md` and its studies
  (`studies/2026-08-26-bm25-storage/`, especially
  `prototype-benchmark.md` — the prototype under `prototype/` is the
  design's executed reference, not code to copy into `src/`).
- **Date:** 2026-08-26
- **Owner:** Clay Gendron
- **Kind:** derived index in the database backend riding the gram
  epoch; a new Rust engine module in `crates/vfs-core` behind
  `vfs.native` with a byte-identical pure-Python fallback; a client
  scorer; schema and index format bumps.
- **Depends on:** the gram epoch machinery (`indexing.py`), the
  keyset-paged chunk scan and `lexical_stats` export that landed in
  a351e7b, the tokenizer and formula in `models/lexical.py`, the
  posting codec (`models/postings.py`, `crates/vfs-core/src/postings.rs`),
  the `vfs.native` seam and its parity suite (`tests/test_native.py`),
  `ByteBatcher`/`chunked` budgets.
- **Relates to:** spec 132 (the consumer: two rounds + scorer + the
  ladder), spec 131 (the harness's BM25 baseline reads through the
  scorer), spec 137 (`BM25Rerank` is this scorer over chunk texts).

## Intent

One BM25 index that ranks identically on every engine, fits (≈0.9×
content), builds inside ADR 048's 60 s linux-scale target, and is
queried the way grep queries grams: fetch a few rows by key, decode
and rank client-side in the Rust engine. The relational index of the
first landing proved the formula and the referee; this rewrite keeps
both and changes the storage unit from a posting to a block.

## Decided semantics

1. **Tables** (epoch-scoped; `lex_docs` exactly as landed):
   `lex_postings(epoch, term, block_no, doc_count, doc_ids, tfs, dls)`
   PK `(epoch, term, block_no)`, sqlite `WITHOUT ROWID`; `term` is
   `BytewiseString(MAX_TERM_BYTES)`; the three blobs are `LargeBinary`
   with the mysql-family `LONGBLOB` variant grams use. A block holds
   ≤ 128 postings in ascending chunk id: `doc_ids` = delta+varint (the
   gram codec's count-prefixed form), `tfs` and `dls` = plain varints;
   a term's blocks are numbered from 0 in id order. `lex_df(epoch,
   term, df, idf, max_weight, blocks)` is the term's summary row:
   `max_weight` (`Double`) is the term's maximum over its blocks and
   `blocks` (`LargeBinary`) is the **block summary** — per block, in
   block order, the varint delta of its first chunk id from the
   previous block's and its true maximum weight as a little-endian
   `f64`. `lex_stats(epoch, n_docs, avg_dl, k1, b)` pins the constants
   the epoch was weighted under. `lex_terms` is dropped.
2. **Formula** unchanged (Lucene-accurate, k1 = 1.2, b = 0.75, exact
   `dl`). A block's `max_weight` is its **true maximum** — the largest
   `idf · tfc(tf, dl)` over its postings, computed at the drain when
   `idf` and `avg_dl` are fixed (plan.md §2) — never the looser
   `idf · tfc(max_tf, min_dl)` bound, and never a SQL predicate (ADR
   055 pin 2).
3. **Tokenizer** unchanged in rules (`models/lexical.py` stays the
   reference); **ported to Rust** in `crates/vfs-core/src/lexical.rs`,
   driven by tables generated from the interpreter's own `\w`,
   `isupper`, `islower`, `isdigit` and `casefold` (a build-time
   `scripts/gen_unicode_tables.py` emits `lexical_tables.rs`; the
   tables carry the Python and Unicode versions they came from and the
   parity suite fails if the interpreter's classes differ on any
   code point both versions assign). `TOKENIZER_VERSION` is shared by
   both engines.
4. **Build**: one streaming pass in the active engine — the Rust
   `LexicalBuilder` (`add_docs([(chunk_id, content)])` → tokenize,
   count, append to the term's open block, seal full blocks, return
   each doc's `dl`; `finish()` → `N`, `avg_dl`, then per term `df`,
   `idf`, every block's true maximum and the summary blob;
   `next_df_batch(row_cap)` → summary rows and `next_batch(row_cap)`
   → block rows, both in term order) behind `vfs.native`, the
   pure-Python builder byte-identical and the parity pin. Fed by the
   landed keyset-paged scan (`_chunk_batches`), CPU through
   `call_offloaded`, rows written in `chunked` inserts under
   `_LEXICAL_INSERT_ROWS`. Memory: the sealed blocks are held until
   `finish()` (the true maximum needs the final statistics), so
   residency is the compressed index plus the vocabulary — the
   prototype's profile; an arena or a sharded build is the direction
   if a corpus outgrows it, never a declared limit. Rebuilt whole per
   reindex; publish and reclaim unchanged (`epoch_scoped()` lists the
   new table).
5. **Scorer** (`models/lexical.py` + `lexical.rs`, dispatched by
   `vfs.native`): `score_blocks(blocks, idfs, avg_dl, k, *,
   candidates=None)` → ranked `(chunk_id, score)` — decode, BM25 with
   exact `dl`, block-max skipping against the running k-th score using
   each block's summary maximum, optional intersection with a sorted
   candidate id array, deterministic order `score DESC, chunk_id`.
   Both engines accumulate in the same term / block / posting order
   (terms by descending maximum, then block order, then postings), so
   the sums are bit-identical; parity pins equality, not a tolerance.
   **Block selection** (`competing_blocks`, pure Python/numpy — one
   `searchsorted` over the candidates): given a term's summary, the
   round-one candidates and their scores, θ and the other overflowing
   terms' summed maxima, the block numbers that can still change the
   top-k. MaxP to entries over `lex_docs`, the statements and the
   round structure are the caller's (spec 132).
6. **Statistics export**: `lexical_stats` returns each probed term's
   `(df, idf, max_weight, blocks)` — the summary row whole — with the
   epoch's `n_docs`, `avg_dl`, `k1`, `b`.
7. **Format bumps**: `SCHEMA_FORMAT_VERSION` 7 → 8, `INDEX_FORMAT_VERSION`
   3 → 4; block size, codec tag and `TOKENIZER_VERSION` in
   `options_fingerprint()`.

## Scope

In: the table swap, the Rust tokenizer + builder + scorer with their
pure twins and parity pins, the build integration, the true block
maximum and the summary codec, block selection, the stats export
change, the fidelity referee retargeted to the scorer and the
two-round fetch. Out: the verb, its statements and the head-fetch
constant (132), scope resolution and the ladder (132), the overlay
(132), parallel sharded builds (fork), term ids (E2), the client
`dl` array (fork).

## Slices

- **A — the Rust lexical engine**: `lexical.rs` (tokenizer from
  generated tables, block encoder, `LexicalBuilder`, scorer) exposed
  through `vfs._native`; `vfs/native.py` seam entries; the pure-Python
  builder, scorer, summary codec and block selection;
  `tests/test_native.py` parity: tokens, summary and block rows, and
  scores identical on the fixture corpus and the lexical fidelity
  corpus; `uv sync --reinstall-package vfs-py` in the landing note.
- **B — tables and build**: `rows.py` swap and bumps, `build_lexical_epoch`
  on the new builder, reclaim parity, budget referees, ledger rows
  re-derived (L1–L6 anchors move: the scan pin stays, the
  `dl`-as-distinct row targets the scorer, the reclaim row targets
  `epoch_scoped`).
- **C — scorer, stats, referee**: `lexical_stats` with summaries; the
  fidelity referee scores through the scorer (Rust and numpy) against
  the from-scratch pure BM25 — identical top-10 and τ = 1.0 on sqlite
  and every engine leg — and proves the two-round fetch: head blocks
  plus the selected blocks score identically to the whole fetch, at
  k = 10 and at the fusion K; the landing note re-measures the
  4,000-file linux sample (build wall, tokenizer share, bytes per
  posting, RSS) against the first landing's 28.8 s / 120 MB and the
  prototype's 2.6 s / 53 MB, then the full checkout (ADR 048's 60 s)
  with an adversarial all-common query at both k.

## Landing criteria

- `scripts/ci.sh 3.13` green under both engines (`VFS_PURE_PYTHON=1`
  and native); `cargo test -p vfs-core` green; 100 % coverage.
- Engine legs green (postgres, mysql, mssql, oracle): the build lands
  on every dialect, the 600-chunk page pin holds, the referee holds.
- Landing note: build wall on the linux sample and the full checkout
  under the 60 s linux-scale target (≤ ~50 s expected in Rust); bytes
  per posting and per chunk; Rust vs numpy scorer times at 1/3/6
  terms; round-two blocks and bytes at k = 10 and the fusion K on the
  drawn queries and on an all-common query.
- Ledger rows: the block bound (a summary maximum below the block's
  true maximum lets a competitive block be skipped — the two-round
  referee catches it); the fallback drift (a pure-Python scorer change
  that diverges from Rust fails parity); the fingerprint (block size
  or codec tag change forces a rebuild); the summary (a block missing
  from a term's summary, or out of order, leaves a competitive block
  unfetched).

## History

- **Second landing, 2026-08-26 — block postings, summaries, the Rust
  engine.** Landed as decided above. `crates/vfs-core/src/lexical.rs`
  (tokenizer from `lexical_tables.rs`, generated by
  `scripts/gen_unicode_tables.py` from CPython 3.13.11 / Unicode
  15.1.0; builder; scorer) behind `vfs._native` protocol 4;
  `models/lexical.py` holds the pure twins, the summary codec and
  `competing_blocks`; parity pins tokens, summary rows, block rows and
  scores identical (bit-identical sums, `score DESC, chunk_id`) on the
  fixture corpora and a block-spanning fuzz corpus; the class tables
  are checked against the running interpreter on every code point
  both assign. Measured through the live tree
  (`studies/2026-08-26-bm25-storage/prototype/landing_bench.py`,
  results beside it):

  | | 4,000-file sample (32,243 chunks) | full checkout (77,866 files, 674,445 chunks) |
  |---|---|---|
  | lexical build (reindex delta) | **5.2 s** (was 28.8 s; engine alone 2.0 s) | **108 s** (engine ≈ 42 s; tokenizer 14.4 s = 13 %) |
  | tokenizer, Rust vs pure | 0.71 s vs ~5.1 s | 14.4 s vs ~107 s |
  | blob bytes per posting | 4.51 | 4.37 (65.2 M postings) |
  | summary bytes per block | 10.4 | 10.9 (5.18 M blocks) |
  | index bytes (sqlite, all four tables) | 61.5 MB = 1.08× content (was 120 MB) | 817 MB = **0.75× content** |
  | builder residency | +320 MB (487 k terms) | ~5 GB peak (4.82 M terms) |
  | scorer, 3 terms, Rust vs numpy | 0.35 ms vs 4.2 ms | 4.1 ms vs 79 ms (1,579 blocks) |
  | round two, k = 10 (blocks fetched) | 39 % at 3 terms, 37 % at 6 | **9.7 %** at 3 terms, 7.5 % at 6 |
  | round two, K = 1,000 | 100 % | 31 % / 38 % |
  | all-common `struct if` | 281 blocks, 100 % fetched, 2.7 ms | 5,983 blocks (3 MB), 99 % fetched, 75 ms |

  The scale property holds as the review stated it: round-two blocks
  fall from 61 % skipped at 32 k chunks to 90 % at 674 k while a real
  rare term anchors θ, and fetch everything at K = 1,000 on the small
  store; the all-common query fetches its lists. **Missed criterion:**
  the full-checkout build is 108 s against the ≤ ~50–60 s target. The
  engine is inside it (~42 s); the rest is the SQLAlchemy insert path
  at 4.3 µs per row over 10 M summary and block rows (a raw driver
  `executemany` measured 1.4 µs) plus the scan and doc rows — the
  direction is a dialect-aware bulk path for the two big tables, a
  fork, not a redesign. Residency is the vocabulary (~660 B per
  distinct term of per-term structure against ~4.4 B per posting):
  the arena layout named in plan.md is the direction, never a cap.
  Two defects surfaced and fixed on the way: the reindex lease's beat
  task read *any* `conflict` as "lease taken", so a build phase that
  held SQLite's write lock past the beat's retries stopped the run at
  linux scale (the lost verdict now carries an explicit mark); and the
  posting-batch pins matched every table with "posting" in its name.
  Engine legs: see the landing report.
- **First landing, 2026-08-26 (a351e7b)** — the relational index of ADR
  051 pin 3 as written: `lex_terms(epoch, term, chunk_id, tf, weight)`
  scored by an in-engine `SUM(weight)`. Landed green on five engines
  with the fidelity referee at τ = 1.0, a two-pass streaming build
  (the sketched whole-corpus builder would have been an OOM on the
  linux store), and a keyset-paged scan after SQL Server refused a
  write under an open cursor at 2,000 files. Measured: +28.8 s per
  4,000 files (tokenizer 34 %), 32 B/posting, 120 MB — ~9× over the
  linux-scale target; on SQL Server 55× slower and 5× larger than the
  native full-text index. Superseded the same day by ADR 055 after the
  storage research leg; the tokenizer, formula, `lex_docs`/`lex_df`/
  `lex_stats`, the paged scan, the stats export and the referee carry
  forward unchanged.
