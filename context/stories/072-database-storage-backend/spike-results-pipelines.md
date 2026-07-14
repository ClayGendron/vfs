# 072 spike — read/write pipelines: six measurements

- **Date:** 2026-07-13
- **Machine:** Apple Silicon (darwin 25.3.0), Python 3.13.11 via uv,
  SQLite 3.50.4 (stdlib driver), Homebrew PostgreSQL 18.0, local NVMe.
  Single-threaded except the two-writer contention test (2 processes).
- **Scripts:** `spike/bench_versioning.py`, `bench_content_layout.py`,
  `bench_batch_write.py`, `bench_contention.py`, `bench_durability.py`,
  `bench_enumeration.py` — all beside this file; JSON outputs in the
  session scratchpad. Corpus: the existing 495K-doc `corpus.db` from
  `spike-results.md` (real OSS code, avg 3.3 KB/doc).
- **Answers:** the "what only the spike can answer" lists in
  `research-write-pipeline.md` (W3/W4/W5/W7/W8) and
  `research-read-pipeline.md` (R5/R7).

## Bottom line

**Every deferred question resolves in favor of the research docs'
recommendations, mostly with an order of magnitude of headroom.**
Snapshot-every-10 is validated (worst-case reconstruction 5.2 ms at
256 KB; the *write-side* diff costs more than the read-side replay).
The inline-content hazard is measured at **259× WAL amplification** on a
metadata-only update — the separate content table is not an optimization
but a correctness-of-cost requirement, and `page_size=16384` on the
content table is a free 1.6–2.5× on large blobs. The Postgres
move-cycle composition — flagged extrapolation in the research — is now
**observed fact at both READ COMMITTED and REPEATABLE READ**, so the
W6b declared mechanism is mandatory, and the R4 REPEATABLE READ pin
does *not* close it; the advisory-lock shape refuses cleanly with no
aborts. BEGIN IMMEDIATE ran 600 contended ops with zero errors while
DEFERRED produced BUSY_SNAPSHOT upgrades that starved a bare spin-retry
(backoff is load-bearing, not hygiene). `synchronous=FULL` costs 2× per
commit and still clears 6,500 single-op commits/s — pin it. R7 has **no
crossover to find**: sargable LIKE on the materialized path column beats
the recursive CTE at every subtree size and depth (up to 12×), and
shallow listing by `parent_id` equality beats prefix scanning by up to
800× — both halves of the read-doc's position confirmed.

## 1. Version chains (W3 + R5) — snapshot-every-10 validated

Agent-shaped edit chains (1–3 hunks per edit), 40 versions, 5 docs per
size tier, real corpus content. Reconstruction = nearest snapshot +
forward `apply_diff` replay, verified byte-identical at every position.

| doc size | compute_diff (write side) | worst reconstruct i=5 (4 diffs) | i=10 (9 diffs) | i=20 (19 diffs) | stored bytes vs all-snapshots, i=10 |
|---|---|---|---|---|---|
| 1 KB | 0.03 ms | 0.12 ms | 0.25 ms | 0.50 ms | 0.68× |
| 4 KB | 0.06 ms | 0.14 ms | 0.31 ms | 0.62 ms | 0.45× |
| 32 KB | 0.81 ms | 0.41 ms | 0.89 ms | 1.84 ms | 0.16× |
| 256 KB | 10.35 ms | 2.24 ms | 5.15 ms | 10.64 ms | 0.13× |

- **Interval 10 stands.** Worst-case replay is 0.25–5.2 ms across the
  size range — far below any interactive threshold; even interval 20
  stays ≈10 ms at 256 KB. Latency scales linearly in both diff count
  and doc size, no cliffs.
- **The chain's real cost is the write side, as the research doc
  predicted (W3 amendment 4):** at 256 KB, `compute_diff` (10.4 ms,
  difflib SequenceMatcher) costs 2× the worst-case read replay. The
  fallback direction recorded in the doc (store-full on write, batch
  delta compression later — git's shape) becomes worth revisiting only
  for docs ≳100 KB under write-heavy load; at the corpus-typical 4 KB
  everything is deep sub-millisecond.
- Storage: diffs+snapshots at interval 10 cost 13–68% of the
  all-snapshots strategy (small docs diff poorly — headers dominate;
  big docs diff superbly). Tightening the interval to 5 costs little
  extra space and halves worst-case replay — a tuning note, not a
  design change.

## 2. Content layout (W4) — the 259× inline hazard, measured

Three layouts × four sizes, SQLite WAL, `synchronous=NORMAL`,
`wal_autocheckpoint=0` (WAL growth = clean write-amplification proxy),
one implicit transaction per op. "Width-flip" alternates the revision
integer between 1-byte and 3-byte serial classes — any metadata column
changing encoded length has the same effect.

| layout | metadata bump (same-width) | bump (width-flip) 1 MB | WAL B/op (flip, 1 MB) | read 1 MB | rewrite 1 MB |
|---|---|---|---|---|---|
| inline (blob in entries row) | 0.011→0.43 ms (grows w/ size) | **2.27 ms** | **1,067,080** | 0.21 ms | 2.09 ms |
| separate (content table) | 0.011 ms flat | 0.011 ms | **4,120** | 0.21 ms | 2.10 ms |
| chunk rows (~4 KB) | 0.011 ms flat | 0.011 ms | 4,120 | 0.53 ms | 3.73 ms |

- **The disqualifying hazard is real and exactly as sourced:** a
  metadata-only update that changes the record's byte size rewrites the
  entire overflow chain — 1.07 MB of WAL to bump one integer next to a
  1 MB blob (**259× amplification**; 35× at 128 KB, 7× at 16 KB). The
  same-width path stays in place (4,120 B at every size) but its
  latency still grows 40× with blob size. The separate table is flat at
  every size on every metadata op.
- **One-blob-per-row beats chunk rows for whole-document verbs:**
  chunked reads are 2.6× slower at 1 MB (reassembly) and rewrites 1.8×
  slower (delete+insert B-tree churn). The id-keyed chunk fallback
  stays recorded, not built.
- **`page_size` grid (separate table):** 16384 vs 4096 gives 1.6×
  faster 1 MB reads (0.13 vs 0.21 ms), 2.5× faster 1 MB rewrites
  (0.86 vs 2.11 ms), for +1.9% WAL bytes. The cheapest lever available,
  as predicted; 16384 is the content-table default to adopt.

## 3. Batch writes (W5) — the criterion matters on the wire, not in-process

One batch = 1,000 entries × (entry row + 3.3 KB content row + version
snapshot row) = 3,000 rows, ~7 MB, in ONE transaction. Best of 3.

| strategy | SQLite | Postgres |
|---|---|---|
| per-row execute (3,000 stmts) | 31.3 ms | 201.3 ms |
| executemany (3 prepared) | 31.0 ms | **105.4 ms** (pipelined) |
| multi-row VALUES @ budget | 35.8 ms (3 stmts) | 142.4 ms (3 stmts) |
| multi-row VALUES @ 999 legacy | 37.9 ms (14 stmts) | — |
| COPY | — | 153.5 ms (3) |

- **In-process SQLite is indifferent to statement count inside one
  transaction** (31–38 ms across a 1000× statement-count range) — the
  historical 50× lesson was about transaction-per-row and ORM
  unit-of-work overhead, not statement count. The restated W5
  criterion (O(tables) statements per parameter-budget chunk) is
  correct *as a dialect-budget rule*, and the budget's purpose is
  wire dialects: Postgres pays 2× for per-row round trips.
- **Pipelined executemany is the Postgres winner at this scale**;
  COPY's setup overhead is not repaid at 1K rows (it wins at bulk-load
  scale, per `spike-results.md` §4's 495K-doc loads). The multirow
  shape is never worse than 1.4× the best — a fine portable default.

## 4. Contention (W7) — IMMEDIATE is clean; the Postgres cycle is real

**SQLite, two OS processes × 300 read-then-write transactions, one
database, `busy_timeout=5000`:**

| mode | BUSY | BUSY_SNAPSHOT | retries (max/op) | p50 | p99 | max |
|---|---|---|---|---|---|---|
| BEGIN IMMEDIATE | 0 | 0 | 0 | 0.06 ms | 2.2 ms | 40 ms |
| BEGIN DEFERRED | 2 | 4 | 6 (6) | 0.06 ms | 0.18 ms | 33 ms |

- **BEGIN IMMEDIATE: zero errors in 600 contended ops** — busy_timeout
  absorbed everything, BUSY_SNAPSHOT unreachable, exactly the sourced
  claim. DEFERRED produced the predicted in-transaction upgrade
  failures (4× BUSY_SNAPSHOT, 2× BUSY) that busy_timeout does **not**
  absorb.
- **Backoff is load-bearing:** the first run's bare spin-retry
  (rollback → immediate re-attempt) starved one worker past 100
  consecutive failures against a tight-loop rival. Whole-op retry with
  even quadratic-millisecond backoff converges in ≤6 attempts. The §10
  retry classifier needs a backoff clause, not just a kind split.

**Postgres, two transactions each running the in-snapshot ancestry
check (recursive CTE) then moving one directory (a→under b, b→under a),
interleaved:**

| isolation / mechanism | outcome |
|---|---|
| READ COMMITTED | both commit — **parent-pointer cycle in the table** |
| REPEATABLE READ | both commit — **cycle** |
| SERIALIZABLE | one aborts (40001), no cycle |
| READ COMMITTED + `pg_advisory_xact_lock` + re-check | second mover's re-check sees the new topology and **refuses**; no abort, no cycle |

- **The research doc's one unobserved extrapolation is now observed
  fact.** Both pre-checks pass in-snapshot, both updates touch
  different rows (no write-write conflict), both commit, and `a↔b` is
  a committed cycle that would break path regeneration and the §7 CTE.
- **The R4 REPEATABLE READ pin does not close the W6b hole** —
  measured directly. The declared serialization mechanism is
  mandatory on Postgres. Of the two working mechanisms, the advisory
  lock is the recommendation: it refuses deterministically with no
  serialization aborts to classify-and-retry, and it scopes naturally
  per mount.

## 5. Durability (W8) — FULL costs 2×, still 6.5K commits/s

Representative op per transaction: entry + version + 3.3 KB content
insert + parent revision bump. 500 sequential commits per cell.

| synchronous | ops/txn | commit p50 | commit p99 | throughput |
|---|---|---|---|---|
| NORMAL | 1 | 0.045 ms | 0.26 ms | 13,065 ops/s |
| FULL | 1 | 0.084 ms | 2.12 ms | 6,509 ops/s |
| NORMAL | 10 | 0.27 ms | 0.44 ms | 27,019 ops/s |
| FULL | 10 | 0.34 ms | 0.63 ms | 22,356 ops/s |

- **Pin `synchronous=FULL`.** The per-commit price is 2× at p50 and a
  single-writer ceiling of ~6,500 op-commits/s — two to three orders of
  magnitude above any agent workload, and batching amortizes it to
  within 17% of NORMAL anyway. The measured trait choice the write doc
  asked for: FULL by default; NORMAL-with-declared-window is available
  as deployment tuning, not the default.
- **Caveat (disclosed):** macOS `fsync()` does not force platter flush
  (SQLite would need `PRAGMA fullfsync=ON` for that, and Linux fsync
  on server hardware typically costs 0.5–2 ms). Absolute numbers
  understate worst-case hardware; the *ratio* and the conclusion — the
  durable default is affordable — are robust, but re-price on target
  deployment hardware before publishing throughput claims.

## 6. Subtree enumeration (R7) — no crossover; LIKE wins everywhere

Real tree from the corpus's file paths: 185,707 nodes (22,295 dirs,
163,412 files), option-(c) shape — `parent_id`, `UNIQUE(parent_id,
name)`, unique index on the materialized `path`, binary collation
(`case_sensitive_like=ON`, the R3 prerequisite doing double duty).
Best of 5, warm.

| subtree | descendants | depth | count: LIKE | count: CTE | rows: LIKE | rows: CTE |
|---|---|---|---|---|---|---|
| fastapi/docs/en/data | 10 | 4 | 0.00 ms | 0.01 ms | 0.01 ms | 0.01 ms |
| gitlabhq/app/models/packages | 100 | 4 | 0.01 ms | 0.03 ms | 0.04 ms | 0.08 ms |
| gitlabhq/config/events | 996 | 3 | 0.03 ms | 0.29 ms | 0.32 ms | 0.80 ms |
| linux/Documentation | 11,011 | 2 | 0.23 ms | 3.65 ms | 3.62 ms | 9.48 ms |
| linux | 83,981 | 1 | **2.44 ms** | **29.31 ms** | 30.4 ms | 81.0 ms |
| deep-narrow (jackrabbit, d=15) | 6 | 15 | 0.01 ms | 0.01 ms | 0.01 ms | 0.01 ms |

Shallow listing (children of one directory):

| directory | children | subtree size | `parent_id = ?` | LIKE + depth filter |
|---|---|---|---|---|
| linux/Documentation | 78 | 11,011 | 0.025 ms | 1.09 ms (44×) |
| linux | 25 | 83,981 | 0.009 ms | 7.16 ms (**795×**) |

- **There is no crossover.** Sargable prefix LIKE on the indexed path
  column beats the recursive CTE at every measured size (12× on counts
  at 84K descendants, 2.7× on full-row fetch) and at depth 15 as well —
  CTE cost scales with per-row index probes; LIKE is one contiguous
  index range scan. The deep-enumeration engine is **path-prefix LIKE
  on the path cache**, with LIKE-metacharacter escaping (already
  doctrine) and binary collation as prerequisites; the recursive CTE
  remains the graph-verb engine (§7), not the enumeration engine.
- **The shallow-list rule is confirmed at 795×**: `parent_id` equality
  only, never prefix-scan-and-filter (the libsqlfs scar, quantified).
- This is also the measured payoff of the R1/W6 materialized-path-cache
  amendment: the column LIKE scans is the one option (c) keeps as a
  regenerable cache.

## What this changes in the research docs and spec deltas

1. **W3/R5 (versioning):** interval 10 confirmed as a read-cost bound;
   the write-side finding (diff costs 2× the worst read replay at
   256 KB, plus a prior-content read inside the write transaction)
   drove an owner decision 2026-07-13 to invert W3's recommendation —
   versions now store **full at write** and a batch **pack verb**
   rewrites cold ranges into the snapshot-every-10 + diff form
   (spec.md §9). The compute_diff column in §1 prices the pack verb's
   batch work; the reconstruction columns price the packed read tier.
2. **W4 (layout):** all three deltas confirmed with numbers; add
   `page_size=16384` on the content table as the concrete default
   (spec delta 7 gains a sentence).
3. **W5 (batch):** restated criterion confirmed; clarify its rationale
   as wire-dialect round-trip cost (Postgres 2×), with in-process
   SQLite indifferent — the budget is a correctness ceiling there, not
   a performance lever.
4. **W7/W6b (contention):** BEGIN IMMEDIATE discipline confirmed
   (0 errors); retry classifier gains a mandatory-backoff clause
   (bare spin starves). **The move-cycle hole is observed, not
   extrapolated — remove the extrapolation flag; REPEATABLE READ does
   not close it; recommend the per-mount advisory lock** as the
   Postgres mechanism in spec delta 3 (deterministic refusal, no
   aborts to retry).
5. **W8 (durability):** pin `synchronous=FULL` in spec delta 5 with
   the measured 2×/6.5K-ops-per-s price; keep NORMAL as declared
   deployment tuning; disclose the macOS-fsync caveat beside the
   numbers.
6. **R7 (enumeration):** resolve the open question — deep enumeration
   is path-prefix LIKE, shallow is parent_id equality, CTE is for
   graph only; read-doc spec delta 9 loses its "chosen by the spike"
   hedge.

## Honest limitations

- Single machine, warm caches, NVMe, no concurrent read load during
  timing runs; contention test is 2 writers (the arbitration-shape
  question), not a throughput scaling study.
- macOS fsync semantics understate absolute durability cost (§5
  caveat); Linux server numbers will differ in level, not ranking.
- Version-chain edits are synthetic agent-shaped hunks (1–3 per
  version); pathological editors (whole-file rewrites per version)
  would push toward the snapshot path automatically.
- The enumeration tree is 186K nodes (deduped files from the 495K-doc
  corpus); the LIKE-vs-CTE gap grows with subtree size, so larger
  trees only widen the verdict. Postgres enumeration was not run —
  the same index-range-scan vs per-row-probe structure applies, but
  the constants are unmeasured.
- Batch-write timings use raw drivers (sqlite3, psycopg); SQLAlchemy
  Core adds per-statement overhead that strengthens, not weakens, the
  few-large-statements discipline.
