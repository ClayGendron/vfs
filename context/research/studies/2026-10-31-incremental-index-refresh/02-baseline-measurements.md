# Baseline: what a whole-corpus reindex costs today, and what staleness costs readers (SQLite, laptop)

Measured 2026-10-31 on Apple M1 Pro (10 cores, 32 GB), Python 3.13.11, SQLite via aiosqlite, vfs at commit 3667fec. Corpora of 10,000 and 50,000 synthetic prose files (mean 6.7 KB, 200-2,000 words). Scripts and raw JSON sit beside this file; `make_tables.py` renders every table in the appendix from the JSON.

## Summary

1. A full `reindex()` costs 13.5 s at 10k files and 136 s at 50k files. It splits roughly in three: chunking the dirty files (8.7 s / 59 s), the gram build (0.5 s / 5 s) and the lexical BM25 build (3.6 s / 64 s). The lexical build is the part that grows worst: 18x for 5x the files. Peak process RSS was 1.05 GB at 10k and 2.8 GB at 50k, because the builders hold the whole posting set in memory.
2. The embed step was a no-op (no provider configured): the result carries no `embedding` extra and no embed statements were issued.
3. Hypothesis B confirmed: a rebuild with 1% dirty costs the same as the cold build. 10k: 12.9 s vs 13.5 s cold (0.96x). 50k: 169 s vs 136 s cold (1.24x). 5% dirty: 0.79x and 0.94x. The only incremental phase today is chunking (0.16 s at 1% vs 8.7 s cold); the `build_epoch` phase (gram + lexical) is rebuilt whole and in fact cost 1.6x to 2.6x the cold build of the same phase, because it slows down with every epoch minted (see "Epoch drift").
4. The "no-op" reindex is not free: 24 statements, 0.5 s / 3.8 s right after the cold build, but 2.1 s / 24 s after four epochs on the same store (and 30 s under cProfile at 50k). The time is not SQL: it is the segment and edge re-convergence passes decoding every segment row in Python (383k UUID decodes, 9.7 s of 30 s at 50k). A 5-minute cadence would pay this every time.
5. grep staleness tax: the suite of 10 patterns took 1.0 s clean and 4.0 s at 5% dirty on 10k (3.9x); 13.4 s clean and 24-27 s at 1-5% dirty on 50k (2x). Statement counts barely move (+1 to +2 per pattern): the scan tier is set-based, the cost is reading and matching every dirty body. No match was lost. At 50k the 3-letter common word hits the 25,000 candidate budget and, when the store is clean, the record says the overlay was not consulted at all.
6. glean staleness tax: the lexical leg scores at most 500 unindexed entries (`OVERLAY_BUDGET`). The budget record appears exactly when the dirty set passes 500 (at 5% on 10k, at 1% on 50k). A freshly written file whose path sorts last is found by grep at every dirty level, and ranked by glean only while the dirty count is at most 500; from 501 on it is silently absent from the ranking and a warning record is returned. glean wall plateaus at 2-3 s per 5 queries because of the cap.
7. Write latency does not depend on the dirty set: `write()` of 500 entries issues 13 statements whether the store is clean or 5% dirty (10k: 0.16-0.20 s clean, 0.24-0.54 s dirty; 50k: 1.06-1.42 s clean, 1.00-1.38 s dirty). The 10k gap is WAL noise, not index work; the statement count is identical.
8. Builder-only cost of a delta is tiny: 6,000 docs (a 60-minute delta at 100 edits/min, 39 MB of text) take 2.9 s of CPU in total: 1.6 s to chunk, 0.2 s to build gram postings (12.7 MB of blobs), 1.2 s to build the lexical index (21 MB of blobs). A 5-minute delta (500 docs) takes 0.24 s. The full rebuild at 50k is 136 s; so an incremental build of a 1% delta would do about 1/50th to 1/500th of the work the rebuild does today.

One-line version: today every refresh pays the whole corpus (136 s and 2.8 GB at 50k; the 1% rebuild costs the same as the cold one), while the work the dirty set actually needs is under 3 s of CPU; meanwhile readers pay 2-4x on grep and glean silently drops dirty rows past 500.

## A. Full reindex cost

| files | step | wall s | chunk s | gram build s | lexical build s | publish+reclaim s | SQL stmts | executemany rows | posting rows | posting MB | lex_postings rows | lex blob MB | chunk rows | db MB | WAL MB | peak RSS MB |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 10,000 | cold build | 13.5 | 8.65 | 0.47 | 3.62 | 0.08 | 278 | 187,073 | 7,142 | 21.1 | 78,999 | 34.3 | 42,476 | 252 | 84 | 1,051 |
| 10,000 | second run, nothing dirty | 0.48 | 0.00 | 0.00 | 0 | 0 | 24 | 0 | 7,142 | 21.1 | 78,999 | 34.3 | 42,476 | 252 | 84 | 1,051 |
| 50,000 | cold build | 136.0 | 59.16 | 4.98 | 64.37 | 0.48 | 1,225 | 874,723 | 7,142 | 105.9 | 384,003 | 172.4 | 213,799 | 1,247 | 420 | 2,820 |
| 50,000 | second run, nothing dirty | 3.76 | 0.03 | 0.01 | 0 | 0 | 24 | 0 | 7,142 | 105.9 | 384,003 | 172.4 | 213,799 | 1,247 | 420 | 2,820 |

Notes. "gram build s" is `build_epoch` minus the lexical build inside it. "executemany rows" counts parameter sets bound to executemany statements (chunk inserts, posting inserts, lexical inserts, flag flips). The posting row count is 7,142 at both sizes because the synthetic vocabulary has only about 7k distinct trigrams; real prose or code has several times more. Posting bytes (2.1 KB per file) are the meaningful size. Embedding: `result.model_extra` is empty at both sizes, so the embed step did not run (no provider). Second run: `_work_pending` is false, no epoch is minted, no rows written; the 24 statements are the lease, the render probe, the fingerprint check and the segment/edge drift reads.

The no-op gets slower as the store ages. Same 24 statements, measured on the same stores later in the run:

| files | no-op right after cold build | no-op after 4 epochs | no-op profiled with cProfile |
|---|---|---|---|
| 10,000 | 0.48 s | 2.07 s | not run |
| 50,000 | 3.76 s | 24.1 s | 30.3 s (16.3 s on a plain per-statement run) |

Per-statement timing of the 50k no-op sums to under 1 s; cProfile attributes 30.4 s of 31.3 s to `_reconverge` (segment and edge drift collection), of which 9.7 s is 383,192 calls to the UUID column decoder (`rows.py:324 process_result_value`) and the rest is row fetching outside vfs code. Files: `results_noop_50000.json`, `results_noop_cprofile_50000.txt`.

## B. Dirty rebuild vs cold build

| files | step | dirty before | live entries | wall s | wall / cold | chunk s | build_epoch s (gram+lex) | build_epoch / cold build_epoch | SQL stmts | executemany rows | epoch |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 10,000 | cold (all dirty) | 10,000 | 10,205 | 13.5 | 1.00 | 8.65 | 4.08 | 1.00 | 278 | 187,073 | 1 |
| 10,000 | 2,000 new entries | 2,000 | 12,212 | 8.2 | 0.61 | 1.81 | 5.45 | 1.33 | 316 | 174,846 | 2 |
| 10,000 | 5% rewritten + 1,501 new | 2,001 | 13,719 | 10.7 | 0.79 | 2.40 | 6.52 | 1.60 | 351 | 191,896 | 3 |
| 10,000 | 1% rewritten | 100 | 13,719 | 12.9 | 0.96 | 0.16 | 10.52 | 2.58 | 350 | 183,615 | 4 |
| 50,000 | cold (all dirty) | 50,000 | 51,021 | 136.0 | 1.00 | 59.16 | 69.34 | 1.00 | 1,225 | 874,723 | 1 |
| 50,000 | 2,000 new entries | 2,000 | 53,028 | 126.6 | 0.93 | 5.85 | 115.09 | 1.66 | 1,221 | 691,595 | 2 |
| 50,000 | 5% rewritten + 1,501 new | 4,001 | 54,535 | 127.5 | 0.94 | 11.81 | 109.99 | 1.59 | 1,257 | 716,596 | 3 |
| 50,000 | 1% rewritten | 500 | 54,535 | 168.9 | 1.24 | 0.59 | 130.47 | 1.88 | 1,256 | 701,770 | 4 |

Reading. The wall-to-cold ratio sits between 0.6 and 1.24 whatever the dirty fraction, and the executemany row count (rows written) is the same order at 1% as at 100%: the posting and lexical tables are rewritten whole every time. Chunking is the one phase that already scales with the dirty set (0.16 s for 100 files). The hypothesis holds: the rebuild cost does not depend on the dirty fraction. The "entry rows" column includes the directories `parents=True` created (205 at 10k, 1,021 at 50k).

### Epoch drift: the lexical build slows down with every epoch

Repeated 1%-dirty rebuilds on the finished 10k store (`epoch_drift.py`), same 350 statements each, 13,719 live entries throughout:

| epoch | step | wall s | chunk s | gram build s | lexical build s | publish+reclaim s | db MB | WAL MB |
|---|---|---|---|---|---|---|---|---|
| 1 | cold, 10,205 entries | 13.5 | 8.65 | 0.47 | 3.62 | 0.08 | 252 | 84 |
| 2 | 2,000 new | 8.2 | 1.81 | 0.57 | 4.88 | 0.14 | 375 | 88 |
| 3 | 5% + 1,501 new | 10.7 | 2.40 | 0.69 | 5.83 | 0.16 | 439 | 99 |
| 4 | 1% | 12.9 | 0.16 | 1.41 | 9.11 | 0.33 | 452 | 116 |
| 5 | 1% | 33.9 | 0.77 | 4.22 | 23.88 | 0.70 | 453 | 113 |
| 6 | 1% | 29.8 | 0.33 | 2.00 | 21.29 | 1.14 | 453 | 113 |
| 7 | 1% | 39.7 | 0.34 | 5.04 | 30.21 | 0.73 | 454 | 113 |
| - | PRAGMA wal_checkpoint(TRUNCATE) + VACUUM, 2.6 s | - | - | - | - | - | 342 | 0 |
| 8 | 1% after VACUUM | 15.6 | 0.20 | 1.83 | 11.95 | 0.24 | 442 | 114 |
| 9 | 1% after VACUUM | 12.5 | 0.15 | 0.78 | 8.33 | 0.45 | 449 | 114 |

The lexical build went from 3.6 s to 30 s for 1.34x the entries while the main file stayed at 453 MB. VACUUM shrank the file by 110 MB and brought the 1% rebuild back from 30-40 s to 12.5-15.6 s, so about half of the slowdown is SQLite file bloat (reclaimed epoch pages reused from the free list) and half remains: the lexical build is 8.3 s at epoch 9 against 3.6 s at epoch 1 for 1.34x the entries. Each epoch also writes about 100 MB of WAL at 10k (the WAL was 0 after the truncate and 114 MB one epoch later), that is roughly 10 KB of WAL per live entry per rebuild. Epochs 5-7 ran while the 50k study was writing to another file on the same SSD, so part of their jump is contention. This is SQLite-specific behaviour and should be re-measured on Postgres before being taken as a vfs fact; but a design that mints an epoch every 5 minutes (96 a day) must plan for the engine's reclaim and bloat cost, not only for the build.

## C. Reader staleness tax: grep

Ten fixed patterns, default `output_mode="lines"`, `grep_wall_seconds=600` so the 10 s default budget never cut a measurement short. Cells are wall s / SQL statements / files matched; T marks a truncation record.

10,000 files:

| pattern | clean | 0.1% (10 dirty) | 0.5% (50) | 1% (100) | 2% (200) | 5% (500) |
|---|---|---|---|---|---|---|
| rare word `lumentfewi` | 0.015 / 7 / 267 | 0.017 / 8 / 317 | 0.020 / 8 / 318 | 0.018 / 8 / 317 | 0.120 / 8 / 315 | 0.105 / 8 / 321 |
| rare word `nadination` | 0.016 / 7 / 243 | 0.020 / 8 / 311 | 0.024 / 8 / 311 | 0.022 / 8 / 308 | 0.192 / 8 / 302 | 0.105 / 8 / 299 |
| rare word `latachment` | 0.069 / 7 / 264 | 0.049 / 8 / 316 | 0.098 / 8 / 318 | 0.056 / 8 / 319 | 0.232 / 8 / 318 | 0.196 / 8 / 312 |
| mid word (rank 1500) | 0.088 / 8 / 778 | 0.114 / 9 / 920 | 0.120 / 9 / 923 | 0.115 / 9 / 923 | 0.489 / 9 / 927 | 0.282 / 9 / 934 |
| mid word (rank 400) | 0.063 / 7 / 2,369 | 0.085 / 8 / 2,842 | 0.086 / 8 / 2,840 | 0.083 / 8 / 2,840 | 0.239 / 8 / 2,842 | 0.373 / 8 / 2,831 |
| identifier literal | 0.024 / 7 / 736 | 0.034 / 8 / 916 | 0.044 / 8 / 918 | 0.042 / 8 / 922 | 0.134 / 8 / 926 | 0.086 / 8 / 936 |
| identifier literal 2 | 0.024 / 7 / 756 | 0.067 / 8 / 893 | 0.031 / 8 / 892 | 0.033 / 8 / 892 | 0.096 / 8 / 888 | 0.274 / 8 / 894 |
| 3-letter common word `was` | 0.552 / 8 / 9,926 | 0.752 / 10 / 11,911 | 0.683 / 10 / 11,911 | 0.836 / 10 / 11,913 | 1.535 / 10 / 11,914 | 1.756 / 10 / 11,917 |
| regex `parse_entry_9\d\d` | 0.057 / 7 / 767 | 0.076 / 8 / 911 | 0.069 / 8 / 914 | 0.082 / 8 / 917 | 0.258 / 8 / 915 | 0.349 / 8 / 909 |
| regex `score(Query\|Handle)[0-9]+` | 0.123 / 8 / 4,155 | 0.154 / 9 / 5,006 | 0.192 / 9 / 5,005 | 0.183 / 9 / 5,007 | 0.473 / 9 / 5,017 | 0.478 / 9 / 4,999 |
| suite total wall s | 1.03 | 1.37 | 1.37 | 1.47 | 3.77 | 4.00 |

50,000 files:

| pattern | clean | 0.1% (50 dirty) | 0.5% (250) | 1% (500) | 2% (1,000) | 5% (2,500) |
|---|---|---|---|---|---|---|
| rare word `lumentfewi` | 0.067 / 7 / 1,331 | 0.135 / 8 / 1,382 | 0.172 / 8 / 1,378 | 0.813 / 8 / 1,379 | 0.841 / 8 / 1,376 | 0.176 / 8 / 1,384 |
| rare word `nadination` | 0.120 / 7 / 1,353 | 0.170 / 8 / 1,420 | 0.204 / 8 / 1,424 | 0.608 / 8 / 1,419 | 0.729 / 8 / 1,419 | 0.555 / 9 / 1,417 |
| rare word `latachment` | 0.225 / 9 / 1,271 | 0.612 / 10 / 1,326 | 0.543 / 10 / 1,323 | 1.275 / 10 / 1,326 | 1.701 / 10 / 1,330 | 1.715 / 10 / 1,314 |
| mid word (rank 1500) | 0.895 / 12 / 3,898 | 1.144 / 13 / 4,043 | 1.259 / 13 / 4,054 | 3.010 / 13 / 4,053 | 4.010 / 13 / 4,060 | 3.179 / 13 / 4,071 |
| mid word (rank 400) | 0.788 / 9 / 11,818 | 0.851 / 10 / 12,286 | 0.974 / 10 / 12,288 | 2.290 / 10 / 12,277 | 3.101 / 11 / 12,281 | 1.759 / 11 / 12,282 |
| identifier literal | 0.250 / 7 / 3,840 | 0.225 / 8 / 4,023 | 0.314 / 8 / 4,018 | 1.248 / 9 / 4,021 | 1.210 / 9 / 4,015 | 1.028 / 9 / 4,028 |
| identifier literal 2 | 0.321 / 7 / 3,923 | 0.177 / 8 / 4,062 | 0.485 / 9 / 4,064 | 1.059 / 9 / 4,054 | 1.012 / 9 / 4,056 | 0.598 / 9 / 4,053 |
| 3-letter common word `was` | 6.730 / 11 / 25,000 T | 2.466 / 12 / 25,000 T | 2.909 / 12 / 25,000 T | 8.299 / 12 / 25,000 T | 11.385 / 12 / 24,999 T | 11.874 / 12 / 24,990 T |
| regex `parse_entry_9\d\d` | 1.206 / 10 / 3,926 | 0.993 / 11 / 4,074 | 1.096 / 11 / 4,080 | 1.645 / 11 / 4,075 | 0.572 / 11 / 4,092 | 1.919 / 11 / 4,102 |
| regex `score(Query\|Handle)[0-9]+` | 2.822 / 12 / 20,189 T | 1.244 / 13 / 20,180 T | 1.894 / 13 / 20,141 T | 4.013 / 13 / 20,102 T | 1.952 / 13 / 19,997 T | 4.069 / 13 / 19,691 T |
| suite total wall s | 13.42 | 8.02 | 9.85 | 24.26 | 26.51 | 26.87 |

Truncation records seen. On the clean 50k store, `was` and the second regex return "Truncated: at the candidate budget, with the unindexed overlay not consulted" (every file matches; 25,000 candidates fill `CANDIDATE_BUDGET` and the scan tier is skipped by design). On every dirty state the same two return "Truncated: at the candidate budget" (the overlay was consulted because a few hundred candidates were filtered). No other pattern truncated. Matched-file counts never dropped when the store was dirty (the "files" column grows between clean and dirty because the clean run pre-dates the 2,000 new entries).

Reading. The tax is paid in body reads and matcher work, not in statements: each dirty level adds one or two SELECTs per pattern (the scan tier's path-ordered read plus content fetch, chunked by the membership budget), while wall grows 2-4x. On 50k the suite plateaus at about 25 s from 1% to 5% dirty rather than growing linearly with the dirty set; the run was sharing the machine with other agents and I did not have time to isolate whether that plateau is real (matcher offload on the thread pool) or noise. Treat the 2x at 500 dirty as the firm number and the 1%-5% plateau as unconfirmed.

## D. Reader staleness tax: glean (lexical leg only)

Five queries of 2-4 words, `limit=10`. Cells are wall s / SQL statements; T marks the overlay-budget record.

| files | state | dirty | suite wall s | stmts per query | overlay-budget record |
|---|---|---|---|---|---|
| 10,000 | clean | 0 | 0.09 | 8-9 | no |
| 10,000 | 0.1% | 10 | 0.15 | 11-12 | no |
| 10,000 | 0.5% | 50 | 0.17 | 11-12 | no |
| 10,000 | 1% | 100 | 0.84 | 11-12 | no |
| 10,000 | 2% | 200 | 0.78 | 11-12 | no |
| 10,000 | 5% | 500 (+1 fresh = 501) | 1.08 | 11-12 | yes, `{'scanned': 500, 'budget': 500}` |
| 50,000 | clean | 0 | 0.89 | 9 | no |
| 50,000 | 0.1% | 50 | 0.65 | 12 | no |
| 50,000 | 0.5% | 250 | 1.70 | 12 | no |
| 50,000 | 1% | 500 (+1 fresh = 501) | 3.00 | 12 | yes |
| 50,000 | 2% | 1,001 | 2.14 | 12 | yes |
| 50,000 | 5% | 2,501 | 2.20 | 12 | yes |

The record text is: "Truncated: at the overlay budget; narrow the query, add globs or ext filters, or scope with paths", `data={'scanned': 500, 'budget': 500}`, kind `truncated`, severity warning. Per-query numbers are in the appendix.

Freshness of a file written after the last reindex, at the path `/zzz/zzz/last.md` (sorts after every corpus path), holding the unique word `qzxvunique`:

| files | dirty files incl. X | grep finds X | glean ranks X | glean record |
|---|---|---|---|---|
| 10,000 | 11 / 51 / 101 / 201 | yes / yes / yes / yes | yes / yes / yes / yes | none |
| 10,000 | 501 | yes | no | overlay budget |
| 50,000 | 51 / 251 | yes / yes | yes / yes | none |
| 50,000 | 501 / 1,001 / 2,501 | yes / yes / yes | no / no / no | overlay budget |

So grep never loses the fresh file (the scan tier reads every NOT-encoded body), while glean's lexical leg stops seeing it the moment 500 other dirty files sort before it in path order; the loss is announced by a warning record but the ranking itself is silently short. At the brief's rate (100-500 edits per 5 minutes, 1,250-6,250 per hour) a 1M-file store would cross 500 dirty entries within 5-25 minutes of any full rebuild.

## E. Write latency with and without pending dirty rows

`write()` of 500 new entries (`parents=True`), three repetitions after one untimed warm-up. The first repetition creates new directories, hence 16 statements instead of 13.

| files | store state | rep 1 wall s / stmts | rep 2 | rep 3 |
|---|---|---|---|---|
| 10,000 | clean | 0.203 / 16 | 0.155 / 13 | 0.158 / 13 |
| 10,000 | 5% dirty (2,001 pending) | 0.537 / 16 | 0.263 / 13 | 0.238 / 13 |
| 50,000 | clean | 1.417 / 16 | 1.060 / 13 | 1.309 / 13 |
| 50,000 | 5% dirty (4,001 pending) | 1.004 / 16 | 1.380 / 13 | 1.327 / 13 |

Confirmed: the write path issues the same statements regardless of the dirty set and never touches an index table. The 10k dirty-state walls are higher (0.24-0.54 s vs 0.16-0.20 s) but at 50k the dirty state is equal or faster; the difference is WAL and page-cache state after the preceding reindexes, not index work. Why a 500-entry write costs 1.0-1.4 s at 50k versus 0.16 s at 10k (7x for 5x the rows) was not investigated here.

## F. Cost of just the dirty-set work (builder only, no database)

Real builders (`postings_builder`, `lexical_builder`, `Chunk.split_batch`) fed with synthetic docs and drained; one process, one thread, no SQL.

| docs | ~delta at 100 edits/min | content MB | chunks | chunk split s | gram build+drain s | gram rows | gram blob MB | lexical build+drain s | lex_df rows | lex block rows | lex blob MB | total CPU s |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 100 | 1 min | 0.62 | 405 | 0.027 | 0.010 | 6,109 | 0.21 | 0.022 | 6,201 | 6,333 | 0.39 | 0.06 |
| 500 | 5 min | 3.27 | 2,131 | 0.118 | 0.025 | 6,630 | 1.07 | 0.097 | 6,610 | 8,160 | 1.80 | 0.24 |
| 2,000 | 20 min | 12.89 | 8,462 | 0.494 | 0.077 | 7,129 | 4.21 | 0.398 | 7,993 | 18,038 | 6.97 | 0.97 |
| 6,000 | 60 min | 39.04 | 25,555 | 1.560 | 0.205 | 7,140 | 12.68 | 1.167 | 11,980 | 48,234 | 21.05 | 2.93 |

All three builders are linear in the input. The lexical builder's "docs" are chunk rows (the backend feeds one doc per chunk), so 6,000 files became 25,555 lexical docs. The gram row count is flat at about 7k because that is the whole trigram vocabulary; the blob bytes (2.1 KB per file) are what grows. For comparison the whole 50k rebuild wrote 106 MB of posting blobs and 172 MB of lexical blobs in 136 s; a 5-minute delta's builders produce 2.9 MB of blobs in 0.24 s.

## Method

Driver: `study.py N` writes the corpus in batches of 2,000 (`DatabaseStorage.write(entries=..., parents=True)`), runs `reindex()` cold and again as a no-op, runs the grep and glean suites, writes 500-entry batches for E, then dirties cumulative prefixes of a seeded permutation of the files (0.1%, 0.5%, 1%, 2%, 5%) by rewriting their content with a new seed, re-running the reader suites and the freshness check at each level, and finally runs the 5% and 1% rebuilds. Statement counts come from a `before_cursor_execute` listener on `storage._host.engine.sync_engine`; phase times from wrappers installed on `backend.chunk_dirty`, `build_epoch`, `publish_epoch`, `reclaim_epochs` and `indexing.build_lexical_epoch`; row counts from `SELECT count(*)` on `posting_list`, `lex_postings`, `lex_docs`, `chunks`, `entry`; blob bytes from `sum(byte_size)` and `sum(length(...))`; peak memory from `ru_maxrss`. `builders.py` is F, `epoch_drift.py` the repeated-epoch run, `noop_profile.py` and `noop_cprofile.py` the no-op breakdown, `make_tables.py` renders `tables.md` (the appendix) from the JSON. Corpus: `corpus.py`, seed 20261031, 5,000-word syllable vocabulary with Zipf weights plus 600 code-like identifiers, tree `/dNN/dNN/fNNNNNN.md`.

## Caveats

1. SQLite, not Postgres. Every insert, reclaim and scan went through one SQLite file in WAL mode on a laptop SSD. The epoch drift and the growing no-op are the findings most likely to look different on Postgres/SQL Server/Oracle; the "rebuild cost is independent of dirty fraction" finding is structural (the code re-posts every entry) and will hold anywhere.
2. Shared laptop. Other agents of this study ran on the same machine during the run. Numbers wobble by up to 2x between repeats (the first 10k run, discarded, had a 33.8 s cold build; the reported one 13.5 s). Ratios within one run are more trustworthy than absolute seconds.
3. Synthetic text. About 7k distinct trigrams and 12k distinct terms; real corpora have many more, so posting and lexical row counts here understate production, and the rebuild cost per file is probably a lower bound.
4. Scaling to 1,000,000 files is an extrapolation by 20x from the 50k corpus. Linear scaling gives a cold rebuild of about 45 minutes, 2 GB of posting blobs, 3.4 GB of lexical blobs and a peak builder RSS of tens of GB; the measured lexical build was superlinear (18x for 5x files), so linear is optimistic. I did not run 1M, and 50k already took 136 s per rebuild, which is why the study stopped there rather than at 20k or 1M.
5. Not measured: the embed step with a provider (none configured, by design of the brief), the vector leg of glean, real-engine legs, the scan-tier plateau from 1% to 5% dirty on 50k (see C), and why `write(500)` is 7x slower at 50k than at 10k. The epoch-drift run was only done on the 10k store.

## Appendix: every table rendered from the JSON

See `tables.md` beside this file (`uv run python make_tables.py 10000 50000 > tables.md`).
