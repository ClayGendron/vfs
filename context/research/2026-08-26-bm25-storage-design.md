# BM25 storage for vfs: how to implement the lexical index database-agnostically, the way grep is

- **Status:** executed 2026-08-26 — three prior-art studies and the
  prototype benchmark complete; §5 is the recommendation for the
  decision pass.
- **Question (Clay, 2026-08-26):** spec 130's relational BM25 index
  (one row per `(term, chunk)` with a precomputed weight) ranks
  correctly on five engines but is ~40 bytes per posting and ~1 B rows
  at 10 M chunks, and its build is 55× slower and 5× larger than SQL
  Server's own full-text index. Study how the serious BM25-in-Postgres
  projects store their index, benchmark the alternative shape — one
  row per `(epoch, term, block)` holding compressed postings, the
  shape grep already uses — in Python and Rust and on the Docker
  engines, and form an opinion on how vfs should implement BM25
  database-agnostically, with the Rust engine in `crates/vfs-core`
  where it earns its place.
- **Informs:** an amendment to ADR 051 (pin 3: own term tables; pin 1:
  the fused statement in-engine) and the shape of spec 132 before it
  builds the query statement on the current tables.
- **Studies:** `studies/2026-08-26-bm25-storage/` — `pg_textsearch.md`,
  `paradedb-tantivy.md`, `vectorchord-bestmatch-lucene.md`,
  `prototype-benchmark.md` (+ `prototype/`: scripts, the Rust bench
  crate, `results/*.json`).
- **Sources line:** clones refreshed to their upstream default branches
  2026-08-26 — `pg_textsearch` 648b25c (PostgreSQL licence),
  `paradedb` 7496549 (AGPL-3.0), `VectorChord-bm25` 14fc2a3
  (AGPL-3.0/ELv2), `pg_bestmatch.rs` 0a3b574 (Apache-2.0), `tantivy`
  cce9950 (MIT), `lucene` 0cc09c8 (Apache-2.0). All studied read-only;
  no code copied.

## 1. What grep already does, and why it is the template

The gram index is the existing answer to "a search index on five SQL
engines with no extension":

- **Storage unit = one row per `(epoch, gram)`** holding the gram's
  whole sorted doc-id set as a delta+varint blob (`grams_posting_list`:
  `postings`, `doc_count`, `byte_size`, `encoding` tag), epoch-scoped
  and rebuilt whole per reindex — a regenerable cache, never migrated.
- **Build in the Rust engine** (`crates/vfs-core`: `grams.rs`,
  `postings.rs`) behind the `vfs.native` seam with a byte-identical
  pure-Python fallback pinned by `tests/test_native.py`; the build's
  CPU hops through the offload pool so the loop keeps serving.
- **Query = fetch a few blobs, decode in numpy, intersect
  rarest-first client-side** (`grep.py`: `_posting_meta`,
  `_posting_blobs`, the ladder with its measured per-byte and
  per-candidate costs), then a Python verify over the candidates. The
  engine is asked only for `WHERE epoch = ? AND gram_key IN (…)` — the
  one statement every dialect plans identically.
- **Scope** is an id allow-list intersected with the decoded postings
  (`np.intersect1d`) or a pushed-down predicate, decided by the same
  cost ladder.

Spec 130 took the *other* road for BM25 — score in SQL — because ADR
051's pin 1 wanted the fused statement in-engine. The measured cost
of that road is the subject of this memo.

## 2. Prior art — three studies, one structure

The full studies are in `studies/2026-08-26-bm25-storage/`; this is
the comparison that matters for the decision.

| | pg_textsearch (TigerData) | pg_search / Tantivy (ParadeDB) | VectorChord-bm25 | Lucene (reference) | vfs spec 130 |
|---|---|---|---|---|---|
| storage unit | immutable segment on 8 KB pages: dictionary → posting blocks → skip entries → norms | Tantivy component files as opaque byte chains on 8 KB pages | one sealed segment + a brute-force "growing tape" | segment files | **one SQL row per (term, chunk)** |
| block | 128 postings; u32 id, u16 tf, 1-byte norm inlined | 128 postings; bit-packed deltas + tfs | 128 postings; d-gap bitpacked ids + tfs | 256 docs; FOR/PFOR, bitset for dense blocks | — |
| bytes/posting | ~2.6 (dense), ≥4.5 all-in on MS MARCO v2 | ~1.0–1.5 (est.) | ~1–2 | ~1–2 | **~40** (row + PK + text term) |
| per-block skip metadata | max tf + min norm (20 B) | `(fieldnorm_id, max_tf)` pair, ~0.06 B/posting | one argmax `(norm, tf)` pair + min/max doc | impacts: Pareto frontier of `(freq, norm)` per block, two skip levels | none |
| top-k | Block-Max WAND, threshold from pushed LIMIT | Tantivy BMW; over-fetch × (1 + dead/live) and retry for MVCC | Block-WeakAnd; returns top-`limit` ctids, Postgres post-filters | WAND / ImpactsDISI | `SUM(weight)` in SQL |
| N, avg_dl, df | metapage totals + memtable; df summed over segments per query; idf never stored | summed over segments at query time; deleted docs counted until merge | frozen at flush in a "jump tuple"; new terms score 0 until VACUUM | summed over leaves (`TermStates`) | `lex_stats` + `lex_df` per epoch (frozen) |
| document length | 1-byte SmallFloat (exact ≤39, then ~6–11 % error) | 1-byte Lucene table | 1-byte Lucene table | 1-byte `intToByte4` + a 256-entry per-query cache | exact `dl` per chunk |
| formula | Lucene-exact (k1 1.2, b 0.75) | Lucene-exact | tantivy idf `ln((N+1)/(df+0.5))` | reference | Lucene-exact |
| build | arena + append lists flushed at `maintenance_work_mem`; parallel workers → BufFiles → leader N-way merge (the merge dominates at 138 M docs) | `maintenance_work_mem` split over heap-scan workers, per-worker merges, never cross-worker | whole rebuild in `maintain` at VACUUM | IndexWriter RAM buffer + merges | two streaming passes, plain inserts |
| filters / joins | pushed LIMIT; heap visibility per candidate | only "fast field" predicates pushed; heap fetch per candidate | post-filter (test pins the recall loss) | collector-level | any SQL predicate joins the scoring statement |
| updates | LSM memtable + tombstones + compaction | ctid-log mutable segment, layered background merges | growing tape until sealed | segment merges | **epoch rebuild** |
| tokenizer | `to_tsvector` (no identifier handling; tf truncated to u16) | `source_code` splits camel/snake but drops the whole identifier and keeps 1-char parts | separate `pg_tokenizer.rs` | analyzers | whole + parts, 1-char drop, 64-B cap |
| sizes claimed | MS MARCO v1 8.8 M docs: 1.2 GB / 233 s; v2 138 M: 17 GB / 17 min 37 s on 15 workers | none published | benchmarks commented out | — | 120 MB / 28.8 s per 32 k chunks |

What the three agree on, and what it means for a SQL-row store:

1. **The unit is a block of ~128–256 postings, compressed, with a
   skip summary beside it.** Nobody stores a row per posting. The
   analogue in SQL is one row per `(epoch, term, block_no)` — the
   gram index's shape with a block number added — at ~1–3 bytes per
   posting inside the blob plus one row's overhead per block.
2. **The block summary exists to bound the block's best score without
   decoding it.** Lucene stores a `(freq, norm)` frontier, Tantivy and
   pg_textsearch a `(max_tf, min_norm)` pair, VectorChord an argmax
   pair — all *inputs* to the formula, because their corpus
   statistics move under them (segments merge, avg_dl drifts). vfs's
   epoch freezes `N`, `avg_dl` and every `df` at build time, so the
   bound can be the **exact precomputed `max_weight` of the block, one
   float column** — tighter than any of theirs, and usable *in SQL*
   (`WHERE max_weight >= :threshold`) before the blob is transferred.
   Every study reached this independently
   (`pg_textsearch.md` §10, `paradedb-tantivy.md` §9,
   `vectorchord-bestmatch-lucene.md` §D).
3. **Statistics are frozen per index generation and summed at query
   time where generations are many.** With one generation (the epoch)
   there is nothing to sum: `lex_stats` and `lex_df` stay exactly as
   spec 130 built them.
4. **Every one of them quantizes document length to a byte and pays
   2–11 % score error for it.** vfs does not have to: `dl` is exact in
   `lex_docs`, and the Lucene/VectorChord study shows an exact `dl` can
   ride inside the blob at ~0.5 B/posting (bit-packed from the block's
   minimum), keeping the τ = 1.0 referee intact.
5. **The machinery that needs an index access method — memtables,
   tombstones, LSM compaction, segment pins, per-candidate heap
   visibility, cross-worker merges — exists to support in-place
   mutation.** The epoch rebuild declines all of it by design; the
   price is the rebuild itself, which the Rust engine and a parallel
   ordinal-sharded build address (`paradedb-tantivy.md` §9).
6. **Filters and joins are the weak spot of every AM-based design**
   (post-filtering with recall loss, over-fetch-and-retry, "fast
   field" pushdown only). This is the one place spec 130's SQL scoring
   is genuinely stronger — any predicate joins the statement — and the
   thing a client-scored design must answer with grep's ladder:
   allow-list intersection on decoded ids, or fetch-then-filter with
   a bound on candidates.
7. **Tokenizers in the field are worse than ours for code**
   (`to_tsvector`; a `source_code` tokenizer that loses the whole
   identifier). Keep spec 130's tokenizer; port it to Rust unchanged.

## 3. The prototype benchmark — executed on spec 130's own corpus

Full detail, commands and JSON in `studies/2026-08-26-bm25-storage/prototype-benchmark.md`.
Corpus: the 4,000-file linux sample spec 130's landing note measured
(32,243 chunks, 8.73 M tokens, 487 k terms, 3.09 M postings). "Option
A" is the landed relational index; "Option B" is one row per
`(epoch, term, block_no)` with three varint blobs — delta-coded chunk
ids, tfs, and **exact** dls — plus `(doc_count, max_tf, min_dl)`,
block size 128, built in one pass (the raw bound pair instead of a
finished weight is what lets the build be single-pass).

**Build (sqlite, `WITHOUT ROWID`):**

| | wall | tokenizer share | rows | index bytes | peak RSS |
|---|---|---|---|---|---|
| A — landed, two passes, Python | 28.8 s | 34 % | 3,094,397 | 119.5 MB | vocabulary + batch |
| B — Python, one pass | **9.5 s** | 55 % | 499,590 | **53.1 MB** | 492 MB |
| B — Rust, one pass | **2.62 s** | 18 % | 499,590 | 53.2 MB | 306 MB |

The Rust tokenizer is a port of `models/lexical.py` driven by tables
dumped from the interpreter's own `\w`/`isupper`/`islower`/`isdigit`/
`casefold`, and is **byte-identical on all 32,243 chunks** (0
divergences; 0.46 s vs 5.01 s, 10.9×). The Python and Rust builds
produce byte-identical tables. Blobs cost **4.34 bytes per posting**
(≈1.5 id, ≈1 tf, ≈1.9 exact dl) against Option A's 32; the whole
index is 0.89× the content bytes. Block 64 and 128 tie; 256 spills to
overflow pages on sqlite (+56 %), and 128 is the size the gram index's
readers already handle. Scaled to the full linux checkout: A ≈ 9 min,
B ≈ 3 min in Python, **≈ 50 s in Rust — at ADR 048's 60 s target**.
At 10 M chunks: A ≈ 960 M rows / 28.6 GiB; B ≈ 8–12 M rows / 5–6 GiB.

**Query on sqlite (15 queries × 3 arities, medians):**

| arity | postings touched | A in-SQL `SUM(weight)` | B fetch | B decode+score, numpy (batched) | B block-max skip (Python) | B decode+score, **Rust** |
|---|---|---|---|---|---|---|
| 1 | 235 | **0.043 ms** | 0.016 | 0.064 | 0.091 (0 skipped) | **0.002** |
| 3 | 10,542 | 2.01 ms | 0.089 | **1.11** | 2.68 (65 % skipped) | **0.16** |
| 6 | 11,077 | 2.23 ms | 0.100 | **1.23** | 2.85 (67 % skipped) | **0.18** |

**Agreement:** all 45 queries return exactly Option A's top-10 —
same ids, order, and scores to 9 decimals — from numpy, from the
block-max path, and from Rust (largest pre-rounding difference
3.6 × 10⁻¹⁵); Kendall τ = 1.0 everywhere. Block-max skipping works as
designed (two thirds of blocks — the common term's — never decoded)
but a per-block Python decision loop costs more than the decode it
saves; it pays in Rust and, more importantly, as a *fetch* filter
(65 % of blob bytes need not leave the engine).

**On the four engines** (both options loaded into throwaway
namespaces; plain drivers; medians of 5):

| | Postgres | MySQL | SQL Server | Oracle |
|---|---|---|---|---|
| postings table bytes, B / A | 71 / 326 MB | 45 / 165 MB | 48 / 178 MB | 55 / 208 MB |
| load, B / A | 1.6 / 7.4 s | 7.7 / 29.6 s | 5.0 / 24.9 s (`BULK INSERT`) | 4–5× faster |
| S1 unscoped, 3 terms, B (fetch + numpy) / A (`SUM`) | **2.2 / 3.0 ms** | **2.4 / 5.2 ms** | **5.1 / 6.4 ms** | 4.4 / **2.9 ms** |
| S3 ext-scoped, 3–6 terms, B (score, then semi-join probe of the top candidates) / A (join) | **3.4 / 7.7 ms** | B wins | **8.1 / 17.6 ms** | B wins |
| S5 500-id allow-list | tie | tie | 14.4 / **10.1 ms** | tie |

The fetch is 0.8–1.4 ms on every engine; the numpy score of the same
bytes ran ~3× slower than on sqlite while the emulated SQL Server and
Oracle containers were competing for the client's CPU (stated in the
study) — the Rust scorer removes that term entirely. One-term queries
are a wash on Postgres/MySQL and 0.3–0.4 ms in A's favour on SQL
Server/Oracle. A per-query client-side scope fetch (20 k ids) is
unusable at 8–96 ms — scope must be resolved to ids in SQL and
intersected, or cached per epoch (grep's ladder, §5 point 4). Scoped
top-10s agree 15/15 with Option A on every engine. Two legs did not
complete as first launched (SQL Server's `fast_executemany` load at
~100 k rows/min was killed and rerun with `BULK INSERT`; Oracle needed
`NUMBER(19)` for the id columns) — recorded in the study, nothing from
the killed run used.

## 4. The decision axes

1. **Bytes per posting and rows per corpus** — the number that decides
   10 M chunks.
2. **Build wall and memory** — where the Rust engine earns its place
   (tokenizer + block encode), and whether the two-pass stream stays.
3. **Query time by shape** — unscoped top-k, scoped (ext, segment,
   allow-list), MaxP — with the fetch+decode+score cost model made
   explicit so the glean verb can ladder like grep does.
4. **Ranking fidelity** — bit-for-bit the same top-k as the relational
   tables (the referee), on every engine.
5. **The fused statement** — what in-engine fusion loses if the lexical
   leg scores client-side, and whether the vector leg's in-engine
   distance still fuses with a client-scored lexical list without a
   quality loss (ADR 052's convex combination is a client operation
   over two ranked lists in any case).

## 5. Opinion — implement BM25 the way grep is implemented

**Replace spec 130's `lex_terms` with block postings, build them in
the Rust engine behind `vfs.native` with the pure-Python builder as
the byte-identical fallback, and score client-side — the gram index's
architecture, term for gram.** Concretely:

1. **Storage.** `lex_postings(epoch, term, block_no, doc_count,
   max_tf, min_dl, max_weight, doc_ids, tfs, dls)` PK `(epoch, term,
   block_no)`, block 128, blobs delta+varint (the gram codec's
   family; the dl blob makes a block self-scoring — no `lex_docs`
   probe per candidate). `lex_docs`, `lex_df`, `lex_stats` stay as
   spec 130 built them (`lex_docs` still serves the entry join and
   MaxP). `max_weight` is the exact per-block bound — legal because
   the epoch freezes `N`, `avg_dl` and `df` — and is the one column
   prior art cannot have; it is written by a cheap second statement
   after the pass (`UPDATE … SET max_weight = idf · tfc(max_tf,
   min_dl)` is dialect-portable because it is single-table and the
   formula is arithmetic; or the pass writes `max_tf, min_dl` and a
   Python/Rust finisher fills `max_weight` in `chunked` updates).
   Bytes: **4.3 per posting, ~0.9× content; 2.25× smaller than the
   landed tables; ~5–6 GiB at 10 M chunks instead of ~29 GiB.**
2. **Build.** One streaming pass in `crates/vfs-core` (`lexical.rs`:
   the tokenizer port + block encoder), fed by the same keyset-paged
   chunk scan spec 130 landed, blocks flushed as they fill, rows
   written in `chunked` inserts; the pure-Python builder is the
   fallback and the parity test. Memory is vocabulary-bound (one open
   block per term); ~50 s on the full linux checkout in Rust versus
   ~9 min today — inside ADR 048's target. The tokenizer share falls
   from 34 % to 18 %, so the spec-130 "Rust-port trigger" is answered
   by the same port.
3. **Query.** Two fetches, as grep's `_posting_meta` / `_posting_blobs`:
   `lex_df` for idf (and each term's `max_weight`), then the block rows
   `WHERE epoch = ? AND term IN (…)` — optionally `AND max_weight >=
   :threshold` once a threshold exists (a second round for the common
   term's blocks that can still compete). Decode + BM25 + top-k in the
   Rust engine (0.16 ms at 10 k postings; numpy fallback 1.1 ms; the
   engine's own `SUM` was 2.0 ms on sqlite and 5.2 ms on MySQL). Score
   agreement with the SQL path is exact (45/45, τ = 1.0), so the
   fidelity referee moves over unchanged.
4. **Scope, like grep.** Predicate scopes (ext, segment, kind,
   liveness) and id allow-lists become a candidate id set resolved
   **before** scoring — the segments join / allow-list subquery spec
   132 already planned, just returning ids — intersected with decoded
   postings via `np.intersect1d` / Rust; the ladder decides whether to
   fetch-then-filter or filter-then-fetch by the same cost model grep
   uses (per-byte fetch+decode, per-candidate cost). This is where the
   AM-based designs are weakest (post-filter recall loss, over-fetch
   and retry) and where grep's shape is strongest: an allow-list is
   exact and costs one intersection.
5. **Fusion.** ADR 052's convex combination is a client operation over
   two ranked lists in every design; the vector leg keeps its
   in-engine distance CTE (spec 135), the lexical leg supplies its
   top-K list client-side, and `Fusion.fuse` combines — the "client
   floor" ADR 051 already accepts for MySQL/GENERIC becomes the
   lexical leg's only path on every engine, while the vector leg stays
   in-engine where the engine can do it. What is lost: nothing that
   was measured to matter — the fused *statement* was a means to one
   ranking on five engines, and one Rust scorer with a pure fallback
   is that with fewer moving parts. What is gained: one code path,
   exact scores, the ladder, and an index that fits.
6. **Keep from prior art, decline from prior art.** Keep: block-per-row
   with a skip summary, frozen per-generation statistics, Lucene's
   formula, the two-fetch shape, and Lucene's 256-entry per-query
   norm cache as a Rust micro-optimisation if it ever shows. Decline:
   byte-quantised norms (exact dl costs 1.9 B/posting and keeps τ = 1;
   revisit only if bytes ever outrank fidelity), memtables/LSM/
   tombstones (the epoch rebuild is the alternative), positions
   (phrase queries are grep's job), and `to_tsvector`-style tokenizers
   (ours is better for code; the field's `source_code` tokenizer
   drops the whole identifier).

**What this changes in the record.** ADR 051 pin 3 (own tables) stands
and is strengthened; pin 1 (one fused statement in-engine) is amended
for the lexical leg — in-engine for the vector distance, client-side
for BM25, fused client-side; pin 4's `df` ceiling becomes a query-time
threshold on `max_weight` rather than a vocabulary cut. Spec 130's
tables are superseded by a spec of their own ("130b" — the block
index and the Rust engine) that must land **before** spec 132 builds
the query path; spec 132's lexical statement becomes the two fetches
plus the scoped-id resolution.

## 6. Forks

- **F1 `lex_df` folded into the term's first block row** (−35 % of
  the remaining bytes; one fetch instead of two). Cheap; decide in the
  spec.
- **F2 `max_weight` in SQL as a fetch filter** — measure how often the
  second round is needed on the harness once thresholds exist.
- **F3 parallel build by ordinal shard** (`paradedb-tantivy.md` §9)
  when a corpus outgrows one core's ~50 s per 76 k files; rayon inside
  the engine, concatenation instead of merge.
- **F4 term ids** (ADR 051 E2) — still open; the per-row text key is
  now ~40 % of `lex_postings` on sqlite because most terms are one
  partial block.
