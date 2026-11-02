# Delta segments prototype: measured costs (2026-10-31)

Machine: Apple M1 Pro (10 cores), SQLite in WAL mode, vfs's Rust engine via `uv run`. Base corpus N = 100,000 synthetic prose+code docs, 2–8 KB each (mean 5.0 KB, 504 MB folded text, ~3,000 distinct trigrams per doc). Doc ids 1..N. All scripts and raw JSON sit beside this file.

## Headline

**A delta build is cheap and its cost depends only on the dirty set.** With the real `PostingsBuilder`, folding + feeding + draining + inserting 500 dirty docs (one 5-minute window) takes **0.08 s**. 6,000 docs (one hour) takes **0.6 s**. 25,000 docs (four hours) takes **1.6 s**. The full base of 100,000 docs takes **4.7 s** of index work and 637 MB peak RSS (300 MB of postings). Scaled to the brief's 1M files, the full rebuild is roughly 50 s CPU and ~6 GB RAM; a 5-minute delta stays at a fraction of a second and a few MB. The write path is untouched.

**The reader pays for K mostly in rows, not bytes, and not in kernel time.** With base + 48 deltas (K=48, the worst case for a 5-minute cadence over 4 hours), a query fetches 196 posting rows instead of 4, but only 27% more bytes (the deltas' share of the docs is 24%, and bytes follow docs, not segments). The Rust kernel's time went from 0.3 ms to 0.7 ms (median). Warm, the whole index tier (meta read + blob fetch + kernel) costs about 1–3 ms per query at K=48 on SQLite versus about 1 ms at K=0.

**No new kernel is needed.** The existing `candidate_ids(groups, allow, cap)` already does "union across segments, intersect within": feed it one group per (AND-group, segment) — a doc lives whole in one segment, so AND within a segment's blobs and OR across segments is exactly the right algebra. It is also *tighter* than merging per gram across segments: the per-gram union admits "phantom" candidates whose old body had gram 1 and whose new body has gram 2 (up to 108 per query here). The per-gram Python union (strategy a) costs 20–100 ms per query and should not be built.

**Ghosts are bounded by the edit fraction.** A re-posted doc leaves its old postings in the base. Among candidates, the ghost share was 5.8% on average (max 25%, on a rare query with 4 candidates) when 12% of the base docs had been re-posted. The share tracks the edit fraction times the chance the new body no longer matches. In the brief's scenario (≤ 2.5% of files edited between full rebuilds) ghosts cost ≤ ~2.5% extra candidate fetches (~75 µs each by grep's own pricing).

**Tiering is an optimization, not a necessity, at a 5-minute cadence.** K=48 flat is serviceable. Merging 48 deltas into 10 segments cut rows per query 196 → 44 and the warm meta+fetch to ~1 ms, with kernel time unchanged. But a Python blob merge is slow: 5 s to merge six 500-doc deltas, 12 s for twelve. **Re-building the same docs from content with the Rust builder is 10–20× cheaper than merging their blobs in Python** (0.15 s for 2,000 docs, 0.6 s for 6,000). So the cheapest "merge" is a rebuild of the covered dirty set, or a Rust merge kernel. Dropping tombstoned docs during a merge is free and shrank the output 19% at 20% tombstones.

**BM25 with base-epoch statistics is acceptable until the next full rebuild.** With 5% of docs re-posted, idf drift from ignoring the deltas' df is median 0%, p90 3.2%, p99 8.3% over 124k terms. The one bad case is a term that exists only in the deltas: base df = 0 gives the maximum idf (+307% for a term in 5% of docs), so brand-new vocabulary is over-ranked. Summing per-segment df and N fixes that (+1.6%) at the cost of double-counting re-posted docs (−5% on ubiquitous terms whose idf is ≈ 0 anyway). A lexical delta build of 5,000 docs took 0.83 s.

One-line version: deltas are cheap to build, cheap to read even at K=48 with the kernel as it is, ghosts cost at most the edit fraction, and tiering can wait.

## Tables

### Table 1. Build cost (N = 100,000 base; deltas half re-posts with changed content, half new ids)

| set | docs | doc MB | fold s | feed s | drain s | insert s | index s (sum) | µs/doc | rows | posting MB | (gen s, excluded) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| base N=100000 | 100000 | 504.0 | 0.256 | 3.599 | 0.069 | 0.790 | **4.714** | 47 | 32361 | 300.6 | 19.3 |
| delta 100 | 100 | 0.5 | 0.000 | 0.006 | 0.004 | 0.066 | **0.077** | 772 | 25168 | 0.5 | 0.0 |
| delta 500 | 500 | 2.5 | 0.001 | 0.021 | 0.006 | 0.050 | **0.078** | 156 | 29981 | 2.3 | 0.1 |
| delta 2000 | 2000 | 9.9 | 0.005 | 0.073 | 0.009 | 0.063 | **0.150** | 75 | 32096 | 8.0 | 0.4 |
| delta 6000 | 6000 | 30.0 | 0.016 | 0.347 | 0.018 | 0.241 | **0.623** | 104 | 32358 | 21.6 | 2.4 |
| delta 25000 | 25000 | 125.9 | 0.126 | 1.183 | 0.026 | 0.225 | **1.560** | 62 | 32361 | 79.7 | 6.2 |

Peak RSS during the base build: 637 MB. "gen s" is synthetic text generation and is not index work (in vfs it is the content read). Posting bytes are ~3 bytes per (gram, doc) pair in both base and deltas. Row count per delta is the number of distinct grams in the dirty docs — nearly constant here because the synthetic corpus has only 32k distinct grams (see caveats).

### Table 2. Read cost vs K (medians over the 20 queries; live set = base + K deltas of 500 docs; strategy b: per-segment kernel groups)

| live set | rows/query | meta ms | fetch ms | kernel ms | index tier total ms | total ms (max over queries) | py-union ms (strategy a) | delta share of bytes | ghost % of candidates (mean) | ghost % (max) |
|---|---|---|---|---|---|---|---|---|---|---|
| K=0 | 4 | 25.58* | 0.28 | 0.31 | 27.31* | 53.63* | 0.0 | 0% | 0.0% | 0.0% |
| K=1 | 8 | 2.60 | 0.20 | 0.86 | 3.82 | 16.36 | 28.5 | 1% | 0.1% | 0.3% |
| K=4 | 20 | 3.97 | 0.26 | 0.61 | 4.62 | 33.60 | 29.6 | 3% | 0.4% | 1.2% |
| K=12 | 52 | 18.35* | 0.45 | 0.71 | 23.21* | 67.80* | 20.0 | 9% | 1.2% | 3.3% |
| K=48 | 196 | 28.60* | 1.06 | 0.74 | 32.93* | 65.08* | 46.9 | 27% | 5.8% | 25.0% |
| K=10 tiered (same 48 deltas merged) | 44 | 0.75 | 0.25 | 0.91 | 1.76 | 6.94 | 18.2 | 23% | 5.8% | 25.0% |

\* The `meta ms` column in this run is dominated by cold OS page cache on the 1.1 GB store (each K level touches new pages). A warm re-measurement (`meta_order.py`, 5 repeats) gives **0.51 ms at K=0 and 2.39 ms at K=12** for the meta read. The warm index tier is therefore about 1 ms at K=0 and 2–3 ms at K=12–48. Treat the starred cells as cache noise.

Ghost % at K=48 means 12% of the base docs had been re-posted (48 × 250). The 25% max is one ghost among 4 candidates of a rare query.

### Table 3. Mean read cost vs K (the same data as means, with both strategies)

| K | rows/query | KB/query | fetch ms | kernel(groups) ms mean | kernel(groups) ms max | py-union ms (strategy a) | kernel after union ms | candidates mean |
|---|---|---|---|---|---|---|---|---|
| 0 | 4 | 157 | 0.31 | 0.71 | 3.57 | 0.00 | 0.81 | 38102 |
| 1 | 8 | 158 | 0.41 | 1.92 | 11.95 | 101.62 | 1.29 | 38212 |
| 4 | 19 | 161 | 0.28 | 2.30 | 28.29 | 74.39 | 3.46 | 38549 |
| 12 | 48 | 170 | 0.51 | 1.79 | 12.31 | 98.20 | 2.70 | 39429 |
| 48 | 180 | 210 | 1.04 | 1.36 | 4.47 | 84.63 | 1.79 | 43433 |

Kernel maxima of 12–28 ms at K=1 and K=4 are single outliers (the same queries take 2–4 ms at K=48); medians in Table 2 are the stable figure.

### Table 4. Per-query detail at K = 0, 12, 48 (strategy b; abridged — `tables.md` has every row)

| K | query | AND groups | grams | rows | KB | fetch ms | kernel ms | py-union ms | candidates | phantoms (a only) | verified (sample) | ghost % | other fp % |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 0 | rare-0 | 1 | 4 | 4 | 1.1 | 0.14 | 0.01 | 0.00 | 0 | 0 | 0 | 0.0% | 0.0% |
| 0 | rare-1 | 1 | 4 | 4 | 1.2 | 0.13 | 0.01 | 0.01 | 3 | 0 | 3 | 0.0% | 0.0% |
| 0 | ident-0 | 1 | 4 | 4 | 41.1 | 0.24 | 0.23 | 0.00 | 3944 | 0 | 3000 | 0.0% | 0.0% |
| 0 | ident-3 | 1 | 4 | 4 | 50.1 | 0.19 | 0.24 | 0.00 | 10444 | 0 | 3000 | 0.0% | 0.0% |
| 0 | word-0 | 1 | 3 | 3 | 102.2 | 0.27 | 0.54 | 0.00 | 27689 | 0 | 3000 | 0.0% | 0.2% |
| 0 | word-1 | 1 | 4 | 4 | 332.5 | 0.34 | 1.06 | 0.00 | 82688 | 0 | 3000 | 0.0% | 0.0% |
| 0 | common-kw | 1 | 4 | 4 | 398.4 | 0.34 | 0.95 | 0.00 | 99586 | 0 | 3000 | 0.0% | 0.0% |
| 0 | phrase | 1 | 4 | 4 | 392.1 | 0.38 | 2.29 | 0.00 | 92438 | 0 | 3000 | 0.0% | 68.9% |
| 0 | regex-alt | 2 | 8 | 8 | 471.5 | 0.58 | 3.57 | 0.01 | 99595 | 0 | 3000 | 0.0% | 0.0% |
| 0 | regex-cls | 1 | 1 | 1 | 96.2 | 0.10 | 0.38 | 0.00 | 96160 | 0 | 3000 | 0.0% | 0.0% |
| 0 | regex-alt2 | 2 | 8 | 8 | 330.1 | 0.38 | 2.05 | 0.00 | 34069 | 0 | 3000 | 0.0% | 3.9% |
| 12 | rare-0 | 1 | 4 | 26 | 1.2 | 0.24 | 0.01 | 0.28 | 0 | 0 | 0 | 0.0% | 0.0% |
| 12 | rare-1 | 1 | 4 | 28 | 1.3 | 0.16 | 0.01 | 0.31 | 3 | 0 | 3 | 0.0% | 0.0% |
| 12 | ident-0 | 1 | 4 | 52 | 44.8 | 0.79 | 0.29 | 17.41 | 4170 | 0 | 3000 | 2.8% | 0.0% |
| 12 | ident-3 | 1 | 4 | 52 | 54.7 | 0.31 | 0.40 | 13.07 | 11044 | 0 | 3000 | 2.6% | 0.0% |
| 12 | word-0 | 1 | 3 | 39 | 111.2 | 0.76 | 1.08 | 122.20 | 29093 | 4 | 3000 | 1.9% | 0.3% |
| 12 | word-1 | 1 | 4 | 52 | 360.2 | 0.46 | 4.60 | 359.98 | 85581 | 0 | 3000 | 0.6% | 0.0% |
| 12 | common-kw | 1 | 4 | 52 | 431.3 | 1.23 | 2.44 | 231.99 | 102585 | 0 | 3000 | 0.0% | 0.0% |
| 12 | phrase | 1 | 4 | 52 | 424.4 | 0.53 | 2.40 | 198.15 | 95386 | 1 | 3000 | 2.4% | 68.0% |
| 12 | regex-alt | 2 | 8 | 104 | 510.8 | 0.92 | 12.31 | 263.60 | 102595 | 0 | 3000 | 0.0% | 0.0% |
| 12 | regex-cls | 1 | 1 | 13 | 104.1 | 0.47 | 1.51 | 22.60 | 99155 | 0 | 3000 | 0.1% | 0.1% |
| 12 | regex-alt2 | 2 | 8 | 104 | 358.3 | 0.67 | 2.24 | 169.62 | 35734 | 30 | 3000 | 2.4% | 3.3% |
| 48 | rare-0 | 1 | 4 | 98 | 1.5 | 0.70 | 0.03 | 0.36 | 0 | 0 | 0 | 0.0% | 0.0% |
| 48 | rare-4 | 1 | 4 | 126 | 2.3 | 0.76 | 0.03 | 0.71 | 4 | 0 | 4 | 25.0% | 0.0% |
| 48 | ident-0 | 1 | 4 | 196 | 56.5 | 1.14 | 0.38 | 12.88 | 4920 | 2 | 3000 | 9.2% | 0.0% |
| 48 | ident-3 | 1 | 4 | 196 | 68.5 | 1.19 | 0.47 | 51.02 | 12833 | 0 | 3000 | 8.6% | 0.0% |
| 48 | word-0 | 1 | 3 | 147 | 138.7 | 0.60 | 1.01 | 90.83 | 33537 | 12 | 3000 | 7.7% | 0.1% |
| 48 | word-1 | 1 | 4 | 196 | 444.1 | 1.09 | 2.49 | 276.33 | 94368 | 0 | 3000 | 2.2% | 0.0% |
| 48 | common-kw | 1 | 4 | 196 | 529.7 | 1.27 | 2.93 | 278.32 | 111609 | 0 | 3000 | 0.1% | 0.0% |
| 48 | phrase | 1 | 4 | 196 | 521.4 | 1.31 | 4.47 | 172.63 | 104311 | 1 | 3000 | 8.8% | 60.0% |
| 48 | regex-alt | 2 | 8 | 392 | 628.8 | 1.97 | 3.10 | 138.57 | 111598 | 0 | 3000 | 0.1% | 0.0% |
| 48 | regex-cls | 1 | 1 | 49 | 127.8 | 0.16 | 1.98 | 24.34 | 108138 | 0 | 3000 | 0.6% | 0.1% |
| 48 | regex-alt2 | 2 | 8 | 392 | 443.5 | 2.28 | 2.75 | 85.41 | 40782 | 108 | 3000 | 7.2% | 3.0% |
| 48 | phrase2 | 1 | 4 | 196 | 408.5 | 1.06 | 2.23 | 124.57 | 87543 | 0 | 3000 | 12.3% | 69.6% |

"other fp %" is grep's ordinary gram false-positive rate (e.g. a two-word phrase whose grams are all common), unrelated to deltas. "phantoms" are candidates only the per-gram-union strategy admits. Verification samples 3,000 candidates when the list is longer.

### Table 5. Merging segments (Python decode → set union → re-encode; sqlite streamed `ORDER BY gram_key`)

| merge | tombstoned docs | rows in | MB in | rows out | MB out | (gram,doc) pairs dropped | decode s | union s | encode s | insert s | total s |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 6 × 500-doc deltas → one 30-min segment | 0 | 179502 | 13.4 | 32290 | 11.6 | 0 | 1.88 | 1.09 | 1.51 | 0.11 | **4.98** |
| same, dropping 600 tombstoned docs (20%) | 600 | 179502 | 13.4 | 32212 | 9.4 | 1,781,141 | 1.72 | 1.27 | 1.11 | 0.07 | **4.55** |
| 12 deltas → one 60-min segment | 0 | 359153 | 26.9 | 32358 | 21.5 | 0 | 3.73 | 2.19 | 2.68 | 0.19 | 9.58 |
| 12 deltas → one 60-min segment | 0 | 359557 | 27.3 | 32358 | 21.8 | 0 | 5.06 | 2.74 | 3.60 | 0.21 | 12.67 |
| 12 deltas → one 60-min segment | 0 | 359317 | 27.1 | 32360 | 21.6 | 0 | 4.71 | 2.86 | 3.16 | 0.22 | 12.09 |
| 6 deltas → one 30-min segment | 0 | 179749 | 13.7 | 32290 | 11.9 | 0 | 2.70 | 1.56 | 2.02 | 0.19 | 6.99 |

Building the whole tiered layout (3 × 60-min + 1 × 30-min merges) took 41 s in Python. Compare Table 1: re-indexing 6,000 docs from content with the Rust builder takes 0.62 s, 2,000 docs 0.15 s. The Python merge runs at ~1.2 µs per (gram, doc) pair; the Rust builder at ~15 ns per pair.

### Table 6. Read amplification: 48 flat deltas vs the tiered layout (same 24,000 delta docs; means over 20 queries)

| layout | live segments | rows/query | KB/query | fetch ms | kernel(groups) ms | py-union ms | candidates |
|---|---|---|---|---|---|---|---|
| K=48 flat | 49 | 180 | 210 | 1.04 | 1.36 | 84.63 | 43433 |
| tiered (3×60min + 1×30min + 6×5min) | 11 | 43 | 198 | 0.33 | 1.28 | 40.42 | 43433 |
| K=0 base only (reference) | 1 | 4 | 157 | 0.31 | 0.71 | 0.00 | 38102 |

### Table 7. BM25 idf drift with 5% of docs re-posted (N = 100,000; rewritten docs also carry a new term `hotfixmarker`)

| term | df base | df delta | df true | idf base-only | idf summed | idf true | err base-only | err summed |
|---|---|---|---|---|---|---|---|---|
| hotfixmarker (new vocabulary) | 0 | 5000 | 5000 | 12.2061 | 3.0444 | 2.9956 | **+307.5%** | +1.6% |
| return | 99586 | 4978 | 99580 | 0.0042 | 0.0042 | 0.0042 | -1.4% | -1.1% |
| self | 99992 | 5000 | 99992 | 0.0001 | 0.0001 | 0.0001 | +0.0% | -4.8% |
| none | 99595 | 4977 | 99586 | 0.0041 | 0.0041 | 0.0042 | -2.2% | -1.5% |
| hev (common prose) | 61014 | 3026 | 61015 | 0.4941 | 0.4945 | 0.4941 | +0.0% | +0.1% |
| kjhwi | 11767 | 605 | 11762 | 2.1398 | 2.1385 | 2.1403 | -0.0% | -0.1% |
| znnzjofg (rarer prose) | 2537 | 127 | 2539 | 3.6740 | 3.6740 | 3.6732 | +0.0% | +0.0% |
| ywksonx_mqdguvc (identifier) | 9037 | 468 | 9066 | 2.4038 | 2.4021 | 2.4006 | +0.1% | +0.1% |
| vjyekyy_ejxvo | 1096 | 50 | 1090 | 4.5131 | 4.5173 | 4.5185 | -0.1% | -0.0% |
| fn_13a516 (rare) | 1 | 0 | 1 | 11.1075 | 11.1563 | 11.1075 | +0.0% | +0.4% |

Over all 124,136 terms of the current corpus, |idf(base-only) − idf(true)| / idf(true): median 0.00%, p90 3.18%, p99 8.26%, max 307% (1,161 terms exist only in the deltas). avg_dl base 835.5 vs true 835.9. "summed" = idf(df_base + df_delta, N_base + N_delta), which double-counts re-posted docs. Lexical builder: 17.3 s for 100,000 docs, 0.83 s for the 5,000-doc delta.

## Method

Scripts (run as `cd /Users/claygendron/Git/Repos/vfs && uv run python <script>`):

- `common.py` — corpus generator (`make_doc(doc_id, version)` is deterministic; version 1 is a fully different body), the sqlite table `posting_list(segment, gram_key, postings, doc_count, byte_size)` with PK `(segment, gram_key)` plus a `manifest` table, `build_segment()` over the real `postings_builder()` with the same 1 MiB drain cap as `indexing.py`, a Python varint decoder, grep's rarest-4 gram choice by summed `doc_count` across segments, and the two candidate strategies.
- `exp1_build.py` — Table 1.
- `exp2_read.py` — Tables 2–4: base + 48 deltas; 20 patterns through `build_code_gram_query`; per query one meta statement and one blob statement over `segment IN (...) AND gram_key IN (...)`; strategy (a) decode+union+`encode_postings` per gram then one kernel call; strategy (b) one kernel group per (AND-group, segment); `re.search` verification on the current bodies (3,000-candidate sample) classifying true / ghost (a re-posted doc whose current body does not match) / other false positive. `--reuse` reruns the queries on an existing store.
- `exp3_merge.py` — Tables 5–6: streaming merge, tombstone variant, tiered layout, requery.
- `exp4_bm25.py` — Table 7 with the real `lexical_builder()` (`add_docs`, `finish`, `next_df_batch`).
- `meta_order.py` — the warm meta-read check and the column-order side check.
- `report_tables.py` → `tables.md` (all rows); raw results in `exp{1,2,3,4}_results.json`; logs in `full_run.log`, `full_run2.log`.

Why strategy (b) is sound: a doc's postings for a given version live entirely in one segment. The query asks "does some version of this doc contain all the chosen grams"; that is OR over segments of AND within a segment, which is exactly the kernel's groups semantics. It is a superset of the true match set (verification still runs) and a subset of strategy (a)'s set.

## Caveats

- **SQLite only.** No Postgres/SQL Server/Oracle numbers. On a networked engine the per-row cost of the meta and blob statements will be higher than SQLite's in-process reads, so the rows-per-query column (4 → 196 at K=48, 44 tiered) is the figure to carry over, not the milliseconds. The two IN lists (segments ≤ 49, grams ≤ 4 per group) stay far under the Oracle/SQL Server caps; segments × grams per statement is still bounded and chunkable by `membership_budget`.
- **Small gram universe.** The synthetic corpus has only 32,361 distinct trigrams, so even a 100-doc delta writes 25k rows and the common queries hit nearly every doc (candidates ≫ the 25,000 cap). A real code corpus has millions of distinct grams: delta row counts would be larger (a 500-doc delta might write 100k–300k rows, so the bulk insert, 0.05 s here, becomes the dominant delta cost on a networked DB), per-gram blobs would be smaller, and common-query candidate sets smaller.
- **Wall-clock is single-machine and partly cold-cache.** The `meta ms` column in Table 2 is cache noise (see the starred note and the warm re-measurement). Kernel maxima at K=1/K=4 are single outliers. All timings are one run, not repeated.
- **Deletes are modelled only in the merge experiment** (as tombstones). Exp2 has re-posts and new docs, no deleted docs; a deleted doc's ghost behaves like a re-posted doc whose new body never matches.
- **Ghost verification is sampled** (3,000 of the candidates) and uses `re.search` with IGNORECASE as the "verify"; vfs's matcher is the Rust `ContentMatcher`, but the classification is the same.
- **Generation time is excluded** from build cost (19 s for the base). In vfs this corresponds to the content read, which the full rebuild also pays.
- **Side finding on the table shape.** In both this prototype and vfs's `posting_list`, the `postings` blob column precedes `doc_count` and `byte_size`. On SQLite a meta read must then skip the blob (overflow pages) to reach the two integers: 0.51 ms vs 0.15 ms per meta statement at K=0 with the integers first (3×), negligible at K=12. Postgres TOASTs the blob out of line so this does not apply there. Small, but free to fix in the schema.

## What I could not do

- Measure on Postgres, SQL Server or Oracle (no engines available in this session).
- Measure a native "union-then-intersect" kernel — it turned out not to be needed: the existing kernel's group shape already is that kernel for this design, and the Python union is reported only as the cost of the wrong approach.
- Drive the real backend `reindex()` with segments; the table shape was replicated standalone as instructed.
- Score the lexical leg end-to-end under deltas (only df/idf drift was measured, not top-k changes).
- Repeat runs for confidence intervals; the time budget allowed one full pass (~12 minutes of compute) plus validation at N=5,000.
