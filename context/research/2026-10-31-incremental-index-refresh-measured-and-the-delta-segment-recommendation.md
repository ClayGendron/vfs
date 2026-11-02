# Incremental index refresh: a delta build costs seconds, readers pay for every hour of staleness, and delta segments on the epoch tables are the way to close the gap

Clay asked on 2026-10-31 for "ideas for how indexing could be incremental" for a company running its enterprise agents on vfs with about 1,000,000 files, 1–5% of them edited per day, a full re-index affordable three times a day (8AM, 12PM, 4PM), and "incremental refreshes to the index that could happen every 5, 15, 30, 60 mins that would not increase the time it takes to write files". He asked for a team to test solutions and come back with proposals, with no edits to source. Four agents worked in parallel for about 40 minutes each against `main` at `3667fec`: a prior-art study of ten systems, a baseline measurement of today's reindex and of staleness on 10k and 50k corpora, a prototype that measured delta segments with the real Rust builders and kernel on a 100k corpus, and a design study that worked four options out against the code. The brief every agent received and the four studies are in [the studies folder](studies/2026-10-31-incremental-index-refresh/), with the scripts, raw JSON and logs under its `experiments/`. There is no intention document for this work; the request above is the stated intent. The spec this memo feeds is [refresh, the incremental index verb](../specifications/active/2026-10-31-refresh-the-incremental-index-verb.md).

## How indexing works today

READ, `src/vfs/storage/backends/database/writes.py` `_material_values`: a content write resets three flags on the entry row (`chunked`, `encoded`, `indexable`) and touches no index table. A delete demotes `encoded` and stamps `deleted_at`. The dirty set is `WHERE NOT encoded`, served by the index `ix_vfs_entries_encoded_kind`.

READ, `indexing.py` and `backend.py`: `reindex()` is an admin verb run by one holder of a heartbeat lease on the meta row. It renders binaries, chunks the dirty entries (dirty-bounded), then builds trigram postings and the BM25 lexical index for every `chunked ∧ indexable ∧ live` entry under a fresh epoch number, publishes by flipping `encoded` on the covered (entry, version) pairs and compare-and-setting the pointer `meta.current_gram_epoch` in one transaction, then deletes every epoch-scoped row below the pointer. It then re-converges the path-segment postings and the fs edges, and runs the embed step, which is already incremental (keyset pages over chunks without a vector).

READ, `grep.py` and `glean.py`: readers partition on `encoded`. The index tier intersects posting blobs through the Rust kernel `candidate_ids` and verifies every candidate against its live body. The scan tier reads every admitted `NOT encoded` body and matches it live. glean's lexical leg scores `NOT encoded` bodies as an overlay with the epoch's statistics, at most `OVERLAY_BUDGET = 500` entries per call in path order, then returns a warning record. Both readers detect a moved pointer between two reads and redrive.

## What today's reindex costs, measured

EXECUTED on an Apple M1 Pro with SQLite ([study 02](studies/2026-10-31-incremental-index-refresh/02-baseline-measurements.md)): a cold `reindex()` of 10,000 synthetic prose files (mean 6.7 KB) took 13.5 s, of 50,000 files 136 s. The split at 50k was chunk 59 s, gram build 5 s, lexical build 64 s. Peak process RSS was 1.05 GB at 10k and 2.8 GB at 50k. The lexical build grew 18x for 5x the files.

EXECUTED: a rebuild with 1% of files rewritten cost 0.96x the cold build at 10k and 1.24x at 50k; with 5% rewritten 0.79x and 0.94x. Executemany row counts at 1% dirty were the same order as the cold build. Chunking was the one incremental phase (0.16 s at 1% against 8.7 s cold at 10k). The hypothesis that the index build is whole-corpus regardless of the dirty fraction is confirmed.

EXECUTED: a `reindex()` with nothing dirty issued 24 statements and took 0.5 s at 10k and 3.8 s at 50k right after the cold build, but 2.1 s and 24 s after four epochs on the same store. cProfile attributed 30.4 s of 31.3 s to the segment and edge re-convergence passes, 9.7 s of it to 383,192 UUID column decodes. A refresh that reused `reindex()` would pay this every run.

EXECUTED: repeated 1% rebuilds on the 10k store took the lexical build from 3.6 s to 30.2 s over seven epochs; a VACUUM recovered about half. Each epoch wrote about 100 MB of WAL at 10k. This is SQLite file behaviour and needs its own measurement on the production engines.

INFERRED: linear scaling from 50k puts the cold rebuild of 1,000,000 files near 45 minutes with tens of gigabytes of peak residency. The lexical build measured superlinear, so linear is optimistic.

## What staleness costs the readers, measured

EXECUTED: a suite of ten grep patterns took 1.03 s on a clean 10k store and 1.37, 1.37, 1.47, 3.77 and 4.00 s with 0.1, 0.5, 1, 2 and 5% of files dirty. At 50k the suite took 13.4 s clean and 24–27 s from 1% dirty on. Statement counts moved by one or two per pattern; the cost is reading and matching every dirty body. No match was lost at any level.

EXECUTED: the glean overlay-budget record ("at the overlay budget", data `scanned: 500, budget: 500`) appeared exactly when the dirty count passed 500. A never-reindexed file at a path that sorts last, holding a unique word, was found by grep at every dirty level and ranked by glean only while the dirty count was at most 500; at 501, 1,001 and 2,501 it was absent from the ranking with the warning record present.

INFERRED: at 10,000–50,000 edits over an eight-hour day, a 1,000,000-file store crosses 500 dirty entries within 5–25 minutes of each full rebuild. Under today's design glean's lexical leg is stale for most of the workday.

EXECUTED: `write()` of 500 entries issued 13 statements whether the store was clean or 5% dirty (16 on the first call that creates directories), at both corpus sizes. Writes never touch the index. The constraint "do not slow writes" is met today and every option below keeps the write path byte-identical.

## What a delta build and a delta read cost, measured on a prototype

EXECUTED with vfs's real `PostingsBuilder`, `candidate_ids` and `LexicalBuilder` on a 100,000-document synthetic corpus (mean 5 KB, 504 MB of text) in standalone SQLite tables ([study 03](studies/2026-10-31-incremental-index-refresh/03-delta-segments-prototype.md)): folding, feeding, draining and inserting a delta of 500 documents took 0.08 s; 2,000 documents 0.15 s; 6,000 documents 0.62 s; 25,000 documents 1.56 s. The full base of 100,000 documents took 4.7 s of index work and 637 MB peak RSS. The baseline study's builder-only run agreed: a 6,000-document delta (one hour at 100 edits a minute) cost 2.9 s of CPU across chunking, grams and lexical, against 136 s for the 50k full rebuild.

EXECUTED: with a base plus K deltas of 500 documents each, posting rows fetched per grep query grew linearly with K (4 at K=0, 52 at K=12, 196 at K=48) while bytes grew only with the deltas' share of documents (+27% at K=48 for 24% more documents). Kernel time went from 0.31 ms to 0.74 ms median. The warm index tier cost about 1 ms at K=0 and 2–3 ms at K=12 to 48.

EXECUTED: no new grep kernel is needed. `candidate_ids` ORs its groups and ANDs the blobs within a group, so passing one group per (AND-group, segment) is a union across segments. It is stricter than a per-gram union because a document's postings for one version live whole in one segment; the per-gram union admitted up to 108 cross-version phantom candidates per query here, and its pure-Python form cost 20–100 ms per query.

EXECUTED: ghost postings (old postings of re-posted documents) were 1.2% of candidates with 3% of the base re-posted and 5.8% with 12% re-posted (maximum 25%, one of four candidates on a rare query). Each ghost costs one candidate fetch and verify.

EXECUTED: merging 48 deltas into 10 segments cut rows per query from 196 to 44 with kernel time unchanged. A Python blob merge took 5 s for six 500-document deltas and 12 s for twelve; re-indexing the same documents from their bodies with the Rust builder took 0.15–0.6 s. Dropping tombstoned documents during a merge shrank the output 19% at 20% tombstones.

EXECUTED: scoring deltas with the base epoch's statistics, with 5% of documents re-posted, drifted idf by a median of 0%, p90 3.2%, p99 8.3% over 124k terms. A term absent from the base (df 0) received the maximum idf, +307% for a term present in 5% of documents. Summing per-segment df and N brought that to +1.6% and double-counted re-posted documents by at most 5% on ubiquitous terms whose idf is near zero.

EXECUTED, side finding: in `posting_list` the blob column precedes `doc_count` and `byte_size`, so on SQLite the meta read pays 0.51 ms against 0.15 ms per statement at K=0 (3x) to skip the blob's overflow pages. Postgres stores large values out of line, so this is SQLite-only.

## What the prior art does

READ ([study 01](studies/2026-10-31-incremental-index-refresh/01-prior-art.md), ten systems, licences in the folder's `licenses.log`): Postgres GIN keeps a bounded pending list that readers merge at query time and that autovacuum or a size backstop flushes (`ginfast.c`); deletes are never in the pending list and heap visibility filters them. Lucene and tantivy write an immutable segment per flush, mark deletes in a per-segment live bitset, merge by size tiers (eight per tier in both), and sum df and N across segments at query time, over-counting deleted documents until merge. SQLite FTS5 keeps segment b-trees with automerge and keeps N and avgdl exact by adjusting a totals row on every write, which vfs's write path forbids. pg_textsearch, newer than vfs's August study, added a `compaction` option whose background mode runs on a cron default of every five minutes with a synchronous backstop when a level is full. zoekt's delta shards put changed documents in a new shard and tombstone their paths in older shards; with no merge policy Sourcegraph forces a full rebuild past 150 shards and calls it an interim hack. VectorChord-bm25 scores new terms at zero until VACUUM, the one approach the field shows to be wrong. pgvector HNSW inserts in place and sqlite-vec uses fixed chunks with a validity bitmap, so vector indexes have no segment problem.

INFERRED: the cadence arithmetic. Without merging a four-hour gap holds 48 deltas at 5 minutes, 16 at 15, 8 at 30 and 4 at 60. Factor-8 tiering collapses 48 to about 9 live generations. At 30 and 60 minutes no merge is needed; the full rebuild is the compaction.

## The four options and the recommendation

The design study ([study 04](studies/2026-10-31-incremental-index-refresh/04-design-options.md)) worked four options out against the code. The evidence above weighs them as follows.

INFERRED, option A, delta segments on the epoch machinery, recommended. A new `refresh()` verb takes the lease, runs the dirty-bounded phases (render, chunk, embed), builds gram postings and lexical rows for only the `NOT encoded ∧ chunked ∧ indexable ∧ live` entries under a fresh epoch number marked with its base epoch, and publishes in one transaction: flip `encoded` on the covered pairs, register the segment, bump a new generation counter on the meta row that the readers compare in place of the pointer. Old postings of re-posted entries stay as ghosts, harmless to grep because every candidate is verified. The full rebuild absorbs everything, and the existing reclaim rule (epoch below the pointer) sweeps the deltas because every delta's number is below the next full epoch's. Readers fetch across the live set with `epoch IN (S)` statements that subtract the segment count from their bind budget, and pass one group per (AND-group, segment) to the kernel as it stands. Build memory and CPU are bounded by the dirty set. Write path: unchanged.

INFERRED, option B, a GIN-style flat pending table: option A with a flat manifest and no compaction identity. GIN's own pending list is a small forward list flushed on a trigger, which is A's fold. Nothing gained.

INFERRED, option C, in-place blob patching: a 500-document window touches common-gram blobs totalling 1–3 GB and must do so in one transaction so readers never see a half-patched index; that is TOAST and WAL bloat on Postgres, lock escalation past 5,000 row locks on SQL Server and undo pressure on Oracle. Removing old ids needs the old gram set, which is not stored. Not viable.

INFERRED, option D, cheaper staleness instead of more indexing: paging the overlay to the wall budget instead of the silent 500 cap is worth doing as hygiene, but no overlay change alters the per-query cost class once 10,000–50,000 bodies are dirty.

INFERRED, the cadence this buys. With append-only deltas and no compaction, 30- and 60-minute cadence hold 9 and 5 live segments and need nothing more. 5- and 15-minute cadence hold 49 and 17 and want a fold compaction: re-index the covered entries of several deltas from their bodies into one segment and retire the inputs, which the prototype showed is 10–20x cheaper than merging blobs and drops ghosts without tombstones.

## A latent bug the study found

READ and confirmed in `glean.py`: `_entries_for_chunks` keeps a ranked chunk whenever its entry is still `encoded`, `_chunk_texts` fetches chunk rows by id, and `_observe` indexes `sources.chunks[chunk_id]` with no miss path. A lexical posting that names a chunk row `chunk_dirty` has deleted raises `KeyError`, which `_execute` does not catch. Today the only path to it is the window after a chunk-generation bump re-dirties `chunked` without demoting `encoded` and re-splits the entries, before the publish. Any delta design makes it a steady-state path, so the delta publish must remove the covered entries' `lex_docs` rows from the live set, and the generation re-dirty should demote `encoded` as well.

## Risks the evidence does not retire

INFERRED: reclaim churn on the production engines. At 5-minute cadence the deltas add millions of epoch-scoped rows per four hours that the full rebuild then deletes. The full rebuild already deletes an old epoch of millions of rows, so the order is familiar, but autovacuum on Postgres and LOB churn on SQL Server should be measured on the Docker legs before a cadence is advertised. The SQLite epoch drift measured above is the warning sign.

INFERRED: every statement that carries `epoch IN (S)` must subtract the segment count from its membership chunk; the existing filter bind reserve of 32 is not sized for 49 segments.

INFERRED: glean's round-one fan-out at 49 segments fetches up to 392 head rows for a common term before a compaction lands; the scorer is linear in postings and delta blocks are small, but the row count is new.

INFERRED: the full rebuild's whole-corpus residency is untouched by every option. A gram-range-partitioned build remains the named direction.

## What this memo does not settle

1. The reclaim and bloat behaviour of a day of deltas on Postgres, SQL Server and Oracle: an experiment on the Docker legs with the `db_test` cycle once the refresh verb exists, measuring rows deleted per full rebuild and table size before and after.
2. Whether the fold compaction is needed at 15-minute cadence in production or only at 5: an experiment counting head rows per term and posting rows per gram on a real corpus with 17 live segments, after the first slice lands.
3. The full rebuild's residency at 1,000,000 files: a placeholder for the gram-range-partitioned build, outside this memo's scope.
