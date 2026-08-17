# Storage-organization arithmetic: measured win bounds on the linux store

Field study, 2026-08-17. Store: `linux-bench/linux.sqlite` (93,760 files /
93,664 encoded, 1.221 GB content, gram index 257,012 grams / 133,728,772
(gram,file) postings / 141.5 MB blobs, epoch 1, page_size 16,384, WAL).
Repo untouched at 1b36b4a; all scripts + raw JSON beside this file.
Timings: raw `sqlite3`, RUNS=5 medians; "cold" = fresh `cp -c` clone +
fresh connection (page cache is vnode-keyed, so a new clone defeats it
without sudo); "warm" = second pass on the same connection.

Candidate sets replicate the live pipeline's nomination exactly (folded
gram plan → rarest-≤4 per AND group under the 4 MB posting budget →
intersect → scope filter → 25,000-candidate budget) and reproduce the
2026-08-17 scoped benchmark's matching-line counts to the digit
(2,506 / 3,938 / 13,073).

Bench rows as measured today (`candidates.json`):

| row | nominated | fetched files | fetch bytes | matched files | lines |
|---|---|---|---|---|---|
| mutex_lock @ drivers/gpu/drm/** (smart→-i) | 6,143 | 683 | 93.8 MB | 579 | 2,506 |
| kzalloc @ drivers/net/** | 13,196 | 1,437 | 64.7 MB | 1,437 | 3,938 |
| EXPORT_SYMBOL_GPL @ drivers/** | 4,297 | 2,465 | 111.6 MB | 2,040 | 13,073 |
| copyright -i unscoped (truncated @25k) | 57,785 | 25,000 | 419.9 MB | 24,997 | 40,926 |

(The brief's "~200 MB for mutex_lock@drm" is pre-104; with scope
intersecting before the budget the row now fetches 93.8 MB.)

---

## 1. Chunk-granularity nomination — BIG LEVER

The store already keys `vfs_chunks` by entry identity with
`line_start`/`line_end` and full chunk content (726,817 chunks, ~7.75
per file, ~2 KB budget). Doc ids in postings are `vfs.id`; chunk
postings would use `vfs_chunks.id` the same way.

Fetch-byte bound (`exp1_chunks.json`): "ideal" = bytes of chunks holding
≥1 matching line; "realistic" = chunks whose folded content contains all
chosen grams of ≥1 AND group — what chunk postings + the same rarest-4
ladder would actually nominate (a superset of ideal minus boundary cases).

| row | today | ideal | realistic | reduction |
|---|---|---|---|---|
| mutex_lock@drm | 93.8 MB | 3.2 MB | 3.3 MB | **28.8×** |
| kzalloc@net | 64.7 MB | 5.6 MB | 5.6 MB | **11.5×** |
| EXPORT_SYMBOL_GPL@drivers | 111.6 MB | 12.9 MB | 13.4 MB | **8.4×** |
| copyright -i unscoped | 419.9 MB | 39.3 MB | 39.3 MB | **10.7×** |

Chunk-level gram false positives are negligible (realistic ≈ ideal): the
2 KB chunk is a far sharper gram predicate than the file.

Time translation (mutex_lock@drm, `exp1d_chunk_fetch_time.json` vs
`exp3_clustering.json`): fetching the 1,860 ideal chunk rows costs
**64.2 ms cold / 2.5 ms warm** vs **165.8–178.4 ms cold / 16–17 ms warm**
for the 683 full bodies — a 2.6× cold and 6.9× warm stage win (cold cost
is page-touch-dominated, so bytes alone overstate the time win).

Posting-side cost, 500-file stratified sample (`exp1_chunks.json`,
`exp1c_chunk_blob.json`):

- (gram,chunk) pairs = 1,626,526 vs (gram,file) = 671,987 → **2.42×
  pairs**.
- Encoded blob bytes (sample-local dense ids preserve the corpus delta
  distribution; method validates at 1.146 B/pair vs the store's actual
  1.058): **2.38× blob bytes** → projected index 141.5 MB → ~337 MB
  (content is 1,221 MB, so index goes from 11.6% → ~28% of content).

Cost the design must own (`exp1b_boundary.json`): grams spanning a chunk
boundary are absent from both chunks' local gram sets — naive chunk-local
extraction would silently miss **5 / 15 / 4 / 2** match-holding chunks
per row (0.27% / 0.47% / 0.05% / 0.01%). Non-zero = forbidden false
negatives; the indexer must emit boundary-spanning grams (index each
chunk with a 2-byte tail of its predecessor) or nominate at file level on
boundary hits. Measured, bounded, cheap — but mandatory.

**Verdict: big lever.** 8.4–29× fetch-byte reduction on every heavy row
for 2.4× posting volume, using a table the store already maintains;
the one recall hazard is measured and closable.

## 2. Positional postings — DEAD

500-file sample (`exp2_positions.json`): 5,171,374 trigram occurrences
over 671,987 (gram,doc) pairs → **7.70 positions per posting**.
Delta+varint within doc: 1.55 B/occurrence + ~1 B/pair count header.
Corpus projection (1.221 G occurrences, fold length ratio 1.0):
**+2.03 GB of position data on a 141.5 MB index → 15.3× index size**,
1.7× the size of the content itself. The read side that money buys
(sub-chunk verify targeting) is already delivered ~10× cheaper by
experiment 1.

**Verdict: dead.**

## 3. Content clustering by path — DEAD (on this backend)

mutex_lock@drm bodies, four fetch orders, 5×cold/5×warm
(`exp3_clustering.json`):

| order | cold median | warm median |
|---|---|---|
| pipeline (path batches, uuid within) | 168.8 ms | 17.4 ms |
| path order | 178.4 ms | 17.5 ms |
| surrogate id order | 175.5 ms | 15.9 ms |
| physical rowid order | 165.8 ms | 16.1 ms |

Spread ≈ 7% cold, within run noise — order is irrelevant on NVMe.
Physical scatter measured via dbstat (true page mapping: leaves in path
order = cells in rowid order, overflow chains named per cell): the 683
candidates touch **6,013 pages vs a contiguous minimum of 5,726 —
already 1.05× optimal**. The build inserted in path-walk order, so
path-locality is already physical; big rows live in per-row overflow
chains whose page count no layout changes. Note for the pipeline: raw
sqlite3 returns these 94 MB in 17 ms warm — the live call's fetch cost
is per-byte handling above SQL, not disk layout. Server engines over a
network would change the arithmetic (row-count-shaped round trips), but
that argues for experiment 1's smaller row set, not for re-clustering.

**Verdict: dead** (re-confirm only if a networked backend shows
layout-shaped latency).

## 4. Content-addressed dedup — DEAD

Full-corpus hash pass (stored `content_hash` verified = sha256(utf8);
`exp4_dedup.json`): 382 duplicate groups, **575 redundant copies (0.61%
of files), 3.26 MB redundant bytes (0.27%)** — mostly perf JSON tables.
On the bench rows: 0 duplicate candidates in all three scoped rows; 13
in copyright-unscoped (0.01% of its fetch bytes).

**Verdict: dead** for read-path savings; CAS remains at most a
write-path/storage nicety, unjustified by this workload.

## 5. Case-folded gram family — ALREADY SHIPPED (no remaining win)

The stored index is already a single folded stream and the planner has
no case input: 'copyright' -i and case-sensitive compile to the
identical 7-gram plan, 4 chosen, 237.4 KB of postings read
(`exp5_folding.json`). The -i tax hypothesized by the brief does not
exist; copyright's 712 ms is candidate mass (25,000 files / 420 MB), not
gram expansion. Counterfactual raw-stream index: -i 'copyright' would
need **56 gram lookups (8×)**; and folding *shrinks* the index —
folded (gram,doc) pairs = 89.9% of raw, vocabulary 71.2%.

**Verdict: already banked; zero remaining win.**

## 6. Result caching for repeats — MARGINAL

The spec-104 raw dataset is **not in the repo** — `mine_usage.py`
re-mines `~/.claude/projects/**/*.jsonl` live; re-mined here with
timestamps and session files kept (10,929 invocations now vs the memo's
10,519 — the logs have grown; `exp6_repeats.json`):

- Exact repeat (pattern+globs+paths+types+ci): **8.2%**; pattern-only:
  26.7%. Time locality: 67% of exact repeats land within 1 h of their
  predecessor; only 14% within the same session file.
- Split by expense: single-file-scoped searches repeat at 8.8%;
  **dir-scoped/unscoped (the only shape a cache would meaningfully
  accelerate) repeat at 6.3% — 146 events across ~3 months of logs**,
  and every intervening write invalidates.

**Verdict: marginal** — <7% hit rate on expensive shapes before
invalidation; not worth cache-coherence machinery in a multi-writer SQL
store. (Epoch-keyed posting-level memoization would face the same hit
rate.)

## 7. Line-offset sidecar — DEAD ON ARRIVAL

mutex_lock@drm bodies (93.8 MB, 683 files; `exp7_lineoffsets.json`):
full Rust verify `hit_lines` = **7.6 ms** (of which ~4.9 ms is the
Python-side utf-8 encode at the seam); `count_lines` cap=1 = 6.4 ms.
A single full-body newline scan alone costs **51.7 ms** — 6.8× the
entire verify — proving the core never scans line boundaries wholesale
(it finds boundaries only around hits). A precomputed line-start sidecar
can save at most some fraction of 7.6 ms; the arithmetic caps the win
well under 5 ms.

**Verdict: dead on arrival.** (If anything at this seam is worth money,
it is the 4.9 ms re-encode — bytes-through instead of str at the seam —
not line offsets.)

---

## Ranking by measured-win-per-complexity

1. **Chunk-granularity nomination — the one big lever.** 8.4–29× fetch
   bytes (2.6× cold / 6.9× warm on the fetch stage measured) for 2.38×
   index bytes on an already-maintained table; must add boundary-gram
   emission (measured 0.01–0.47% recall hole otherwise).
2. **Case-folded family — already shipped**; the brief's premise is
   satisfied by the live design (8× lookup saving already banked, index
   10% smaller than raw).
3. **Result caching — marginal** (6.3% exact-repeat on expensive shapes;
   invalidation-heavy).
4. **Content clustering by path — dead** here (store already 1.05× from
   optimal packing; order shifts cold fetch <7%); revisit only with
   networked-engine evidence.
5. **Dedup / CAS — dead** (0.27% of bytes, 0% of scoped bench rows).
6. **Positional postings — dead** (15.3× index for a win experiment 1
   buys at 2.38×).
7. **Line-offset sidecar — dead on arrival** (<5 ms ceiling by
   arithmetic).

## Schema/method caveats and follow-ups

- **Chunk boundary law**: `vfs_chunks` ranges can overlap by one line
  (a chunk may end mid-line); match-line→chunk mapping counted every
  intersecting chunk. A chunk-nomination design needs the same rule.
- **dbstat row→page mapping** relied on btree cell order = rowid order
  (holds: rowids are contiguous, no deletes in this store); a store
  with churn would need the walk redone.
- **Positions estimate** assumes fold preserves byte length (measured
  ratio 1.000 on the sample; ASCII-dominant corpus).
- **Exp-6 dataset is machine-local and single-user**, and includes
  sessions newer than the memo's snapshot; not in the repo — a durable
  study would need the mined records checked in.
- **Timing floor is raw sqlite3**, not the aiosqlite/pipeline stack;
  order comparisons are internally valid, absolute stage times in the
  live pipeline are higher.
