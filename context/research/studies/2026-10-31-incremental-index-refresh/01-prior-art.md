# Prior art: how mature indexes absorb a trickle of updates without slowing writers or rebuilding

Date: 2026-10-31. Scope: inverted (trigram, BM25) and vector indexes under steady small updates; what each system does and what it teaches vfs, whose index is a SQL table of posting blobs keyed `(epoch, gram)`, whose readers union an index tier with a live-scan tier and verify every candidate against live content, and which can afford a full rebuild three times a day. This memo describes prior art and its lessons. It proposes no vfs code.

Sources (all read-only, cited by `path:line`, nothing copied; commits are the local clones as found, not refreshed): `postgres` b128e75 (2026-10-14, PostgreSQL licence, `COPYRIGHT`); `lucene` 4eb488d (2026-09-30, Apache-2.0); `tantivy` d5e2842 (2026-09-29, MIT); `sqlite` 3d17c3f (2026-08-04, public domain, `LICENSE.md`); `pg_textsearch` 710976a (2026-09-27, PostgreSQL licence; 19 commits past the 648b25c vfs studied in August); `paradedb` 0282cc5 (2026-09-28, AGPL-3.0; 185 commits past 7496549); `VectorChord-bm25` 14fc2a3 (2026-04-28, AGPL-3.0 / ELv2 dual; unchanged since the August study); `zoekt` a920600 (2026-08-26, Apache-2.0); `pgvector` 70fb225 (2026-09-30, PostgreSQL licence); `sqlite-vec` 04d28bd (2026-05-17, MIT / Apache-2.0 dual).

Already known in vfs, not repeated here: the BM25 storage memo (`context/research/2026-08-26-bm25-storage-design.md`) decided block-per-row postings, frozen per-epoch statistics and a client-side Rust scorer, and declined memtables, tombstones and LSM compaction because "the epoch rebuild is the alternative" (§5 point 6). Its studies under `context/research/studies/2026-08-26-bm25-storage/` describe pg_textsearch, pg_search and VectorChord's update paths in detail; I cite them rather than re-derive. The August notes under `studies/2026-08-17-search-storage-organizations/` already read GIN's pending list as "the analog of vfs's scan tier" and FTS5's incremental merge as "DOA for posting data" given the epoch swap. The turbopuffer memo (`2026-06-03-turbopuffer-architecture.md`) kept tiered compaction "in pocket". This memo opens the pocket: the question is not whether to replace the epoch rebuild, but what to run between rebuilds.

## 1. PostgreSQL GIN: the pending list

(a) Unit of work. One unsorted chain of pages off the metapage, one index tuple per `(key, heap TID)`, no posting lists; an insert appends to the tail page instead of touching the entry tree (`src/backend/access/gin/ginfast.c:1-8`, `ginHeapTupleFastInsert` :219; motive at `doc/src/sgml/gin.sgml:498-520`).

(b) Readers. Every scan reads the pending list first, linearly, then the tree. The order is load-bearing: tree-first could miss an entry a concurrent cleanup moves; list-first can only visit it twice, which a bitmap tolerates (`ginget.c:1947-1957`). The planner charges the whole pending list as startup cost and trusts `nPendingPages` read live from the metapage (`src/backend/utils/adt/selfuncs.c:8734-8747`).

(c) Deletes. None in the index; readers rely on heap visibility. VACUUM forces a pending-list cleanup first so dead TIDs are in the tree where it can remove them (`ginvacuum.c:657-667`).

(d) Merge trigger. Two. A size backstop fires in the inserting backend when the list exceeds `gin_pending_list_limit` (default 4 MB; `guc_parameters.dat:1197-1204`), deliberately *before* it outgrows one `work_mem` collection cycle, and bails if another backend is already cleaning (`ginfast.c:448-471`, :826). The background trigger is VACUUM or autoanalyze with `maintenance_work_mem` (`ginfast.c:807-830`). Cleanup bulk-inserts the accumulated keys through the index-build path, then unlinks the consumed pages (`ginfast.c:896-980`). The docs prefer background cleanup and offer `fastupdate=off` when "consistent response time is more important than update speed" (`gin.sgml:525-541, 604-610`).

(e) Statistics. Not applicable (set membership).

(f) Bounds. Read cost is linear in pending rows; "a large list of pending entries will slow searches significantly" (`gin.sgml:525-527`). Cleanup is crash-safe by idempotence: post, then unlink; a crash re-posts, never loses (`ginfast.c:767-772`).

Lesson. GIN is the only system here that touches the index on the write path, and it still pays in read fan-out; vfs's flag reset is cheaper than GIN's append. What transfers: the two-trigger merge (cadence plus a size backstop that fires below the cap and yields to a rival), the overlay-first read order stated as an invariant, and charging the overlay honestly as startup cost.

## 2. Lucene and tantivy: immutable segments, live-docs, tiered merging

(a) Unit. A segment per flush. Lucene flushes when the RAM buffer reaches 16 MB by default (`IndexWriterConfig.java:83`; `FlushByRamOrCountsPolicy.java:31-45`); tantivy when a per-thread arena of at least 15 MB fills (`src/indexer/index_writer.rs:29-36, 195`).

(b) Readers. A search opens every segment and unions results. Nothing is merged at read time except statistics (below).

(c) Deletes and updates. A delete never touches postings. It becomes a bit cleared in a per-segment live-docs bitset, written as a new generation file at flush or commit (`ReadersAndUpdates.java:236-242, 290-291`). Tantivy does the same: a delete queue of operations stamped with an opstamp is replayed against each older segment to produce an alive bitset; a delete only affects documents inserted before it (`src/indexer/index_writer.rs:95-124`, `advance_deletes` :131). An update is a delete plus an add into the newest segment, so the old version remains physically present but invisible.

(d) Merge policy. Lucene's `TieredMergePolicy` computes a segment budget — floor 16 MB, 8 per tier, 5 GB cap (`TieredMergePolicy.java:77-83`) — by walking geometrically growing tiers and allowing `segsPerTier` at each (`:396-416`). Only over budget does it pick the cheapest merge, scored by skew, size and deletes reclaimed (`:30-45, 676-723`); segments above half the cap are excused unless over `deletesPctAllowed` (20 %) dead (`:379-388`). Its docstring warns that a low deletes threshold makes indexing "continuously merge nearly all segments" (`:131-136`). Tantivy's `LogMergePolicy` buckets by log2 of doc count (floor 10 000, ratio 0.75) and merges a bucket of 8 or more, or one holding an over-deleted segment (`src/indexer/log_merge_policy.rs:8-14, 94-128`); the policy is consulted after every commit and finished merge (`src/indexer/segment_updater.rs:601-636`).

(e) Statistics. Lucene never merges postings for scoring; it sums statistics. `TermStates` adds `docFreq` across leaves (`TermStates.java:158-163`); `fieldStats` sums `docCount` and `sumTotalTermFreq` (`IndexSearcher.java:1144-1159`); BM25 derives `idf` and `avgdl` from those sums (`BM25Similarity.java:138-145`). Deleted-but-unmerged documents still count in `df` and `N`; the Javadoc defends the error as "in the same direction" (`:160-170`). Tantivy sums `doc_freq` (`src/core/searcher.rs:133-141`) and takes `N` as the sum of `max_doc`, deleted included (`src/query/bm25.rs:38-44`).

(f) Bounds. Per-term read cost is one seek and one cursor per segment, linear in live segments; the tier budget keeps that near `segsPerTier × log_8(index / floor)`. Each document is rewritten about once per tier it climbs.

Lesson. Deletes are an overlay the reader consults, not a mutation of postings; statistics are a sum over generations with the drift accepted and bounded by merge; the tier budget, not a cadence, bounds fan-out.

## 3. SQLite FTS5: segment b-trees in one shadow table

(a) Unit. Each transaction's pending terms sit in an in-memory hash (flush at 1 MiB, `fts5_config.c:23`) and are flushed as exactly one new level-0 segment (`fts5_index.c:5824-5846`, `fts5FlushOneHash` :5614). Segments live as fixed-size leaf blobs in `%_data(id, block)` (`:69-73`); the structure record lists levels and the per-level count of inputs to an in-progress merge (`:82-119`).

(b) Readers. A query opens an iterator per segment and merges them through a loser tree, `log(S)` work per advance (`:621-640`). FTS5's own notes call the fully merged doclist for a common term a memory hazard (`notes-fts5.md` §3).

(c) Deletes. A normal table re-reads the old row, re-tokenizes it and writes delete markers into the newest segment; the marker annihilates the posting when they meet at the oldest level of a merge (`fts5_storage.c:495-520`; `notes-fts5.md:17, 31`). `contentless_delete=1` tables cannot re-tokenize, so each segment carries tombstone hash pages probed per rowid (`fts5_index.c:236-259, 3300-3320`), and `deletemerge` (default 10 %) nominates a level once tombstones reach that share of its entries (`:4932-4975`; `fts5_config.c:25`).

(d) Merge policy. Three knobs. `automerge` (default 4): every 64 leaf pages written to level 0 buys `64 × nLevel` pages of merge work on the level with the most segments, resumable because the structure record remembers how many inputs are mid-merge (`:5034-5053, 4978-5032, 4777`). `crisismerge` (default 16): a blocking backstop on any level holding 16 or more segments, cascading upward (`:5055-5071`). `'merge', N` and `'optimize'` (everything into one, in 1 000-page units) are the manual path (`:5913-5976`; `fts5_main.c:1798-1802`). Caps: 64 levels, 2 000 segments (`fts5Int.h:107`; `fts5_index.c:57`).

(e) Statistics. Exact, not summed: the averages record holds row count and total tokens, adjusted on every insert and delete (`fts5_index.c:119-125`; `fts5_storage.c:581-594`); `df` is counted while iterating. Exact `N` and `avgdl` at any instant, for one small write per row.

(f) Bounds. `S` iterators with `log S` merge cost; `crisismerge` caps `S` per level at 16 and `automerge` keeps it far lower. Merge work is proportional to leaves written, except when the crisis backstop fires, which "may take a long time" (`notes-fts5.md:32`).

Lesson. The resumable merge with a budget tied to bytes written is the cleanest pay-as-you-go compaction in the set; the amortized/crisis/manual trio is a template for a refresh verb's policy surface; exact statistics are cheap only if the write path may touch a totals row, which vfs's may not.

## 4. pg_textsearch: LSM memtable plus paged segments, now with scheduled background compaction

The August study covers the storage, the memtable spill at 64 chain pages, the tiered merge at 8 segments per level, the alive bitset, and the statistics summation (`studies/2026-08-26-bm25-storage/pg_textsearch.md` §§ memtable, 55-57, 67-69, 98-104). What is new at 710976a:

(d) A `compaction` index option with three modes. `inline` compacts in the spilling writer's transaction; the README is explicit that this is "reader non-blocking, not foreground-writer non-blocking" (`README.md:360-369`). `background` dispatches a pre-commit request to a managed workflow that runs "a stepped cascade immediately, then waits for a spill signal or its cron schedule", default `*/5 * * * *` — every five minutes (`README.md:194-195, 415`; `ARCHITECTURE.md:233-262`). `manual` leaves debt to `bm25_compact()`, `bm25_compact_step()` and `bm25_needs_compaction()` (`README.md:371-395`). The trigger is still count-based: any level at `segments_per_level` is a candidate (`src/segment/compaction.c:2288-2302`). One rule survives every mode: a level 0 already at the threshold "blocks the spill outright", so it is compacted in the spilling process regardless, "a background worker's pass would come too late" (`ARCHITECTURE.md:143-150`).

(e) Unchanged: `df` is memtable df plus the sum over every segment on every level (`src/scoring/bm25.c:40-64`); `N` and total length come from metapage totals plus the memtable; deletes over-count both until merge.

(f) Each pass is bounded ("at most one bounded pass", `ARCHITECTURE.md:152-160`); long builds hold no per-index LWLock; displaced pages are parked behind a transaction horizon rather than freed (`ARCHITECTURE.md:264-300`).

Lesson. A production BM25-in-SQL engine moved from synchronous-only compaction to a five-minute scheduled worker in the two months since vfs last looked, while keeping the synchronous backstop for the one case a schedule cannot save. That is the same two-trigger shape as GIN. The cadence it chose is the shortest one in vfs's question.

## 5. ParadeDB pg_search: Tantivy segments on Postgres pages

The August study covers the ctid-log mutable segment (default 1 000 rows, flushed at statement end), the `.del` alive bitsets written only by VACUUM, and the layered merge policy (`studies/2026-08-26-bm25-storage/paradedb-tantivy.md` §§1, 3, 4). Confirmed at 0282cc5: background layers start at 100 KB and step by decades (`pg_search/src/postgres/options.rs:66-69` and following); a candidate closes when its bytes reach `layer + layer/3` and segments larger than the layer are skipped (`pg_search/src/index/merge_policy.rs:252-292`); nothing merges while visible segments are at or under `target_segment_count` (`pg_search/src/postgres/merge.rs:171-202`); more than two mutable segments is backpressure that makes the inserting backend merge in the foreground, otherwise a background worker is launched (`:248-264, 284-313, 337-365`).

(c) Visibility is solved by over-fetch and retry, not by the index: the top-k scan sizes its first fetch by `(1 + (1 + n_dead)/(1 + n_live))` from heap statistics and, when returned rows prove invisible, refetches with a chunk multiplied by `topk_retry_scale_factor` up to a cap (`pg_search/src/postgres/customscan/basescan/exec_methods/top_k.rs:100-115, 347-362, 573-583`).

Lesson. The "verify against the heap and refetch if short" loop is the closest cousin of vfs's verify-every-candidate reader, and pg_search had to add a dead/live scale factor so the first fetch is usually enough. The `target_segment_count` floor — do not merge below the parallelism you want — is a reminder that a handful of segments is a feature, not just a cost.

## 6. VectorChord-bm25: one sealed segment and a growing tape

Unchanged since August (`vectorchord-bestmatch-lucene.md` §A). Inserts append raw vectors to a tape (`crates/bm25/src/insert.rs:23-79`); every query brute-forces the whole tape before running Block-WAND over the single sealed segment (`search.rs:83-135`); `bulkdelete` flips a `deleted` flag; statistics are frozen at the last `maintain`, which runs only at VACUUM (`maintain.rs:27`, `am_vacuumcleanup.rs:39`), so a term that first appears in the tape scores zero until then. This is vfs's scan tier without a budget and without a schedule. Its lesson is negative: an unbounded overlay is a latency cliff, and frozen stats that omit new terms are a recall hole.

## 7. zoekt: whole-shard rebuild, delta shards, and compound shards

(a) Unit. The shard, per repository. `zoekt-indexserver` fetches every repo hourly and runs `zoekt-git-index -incremental`, which skips a repo whose on-disk shard already matches the requested commit and options (`cmd/zoekt-indexserver/main.go:80-84, 90-127, 150-166`; `index/builder.go:366-398`); any change re-indexes the whole repo.

(b)(c) Delta shards are the exception. A delta build writes only changed documents into a new shard numbered after the existing ones and records every changed or removed path as a `FileTombstone` in the older shards' metadata (`index/builder.go:105-107, 586-594, 650-657, 690-700`); search skips a document whose file name is in its shard's tombstone set (`index/eval.go:222-237`; `api.go:652-654`).

(d) Compaction. None for delta shards. Sourcegraph's indexserver forces a full build once a repo exceeds `DELTA_SHARD_NUMBER_FALLBACK_THRESHOLD` shards, default 150, which the code calls a "HACK: for our interim compaction strategy ... obviously isn't optimal" (`gitindex/index.go:441-447, 924-937`; `cmd/zoekt-sourcegraph-indexserver/main.go:1591`). Compound shards serve memory, not freshness: `zoekt-merge-index` packs repos idle for `minAgeDays` into one file on an 8-hour ticker, at an admitted cost of "degraded search performance" (`cmd/zoekt-merge-index/main.go:13-30`; `cmd/zoekt-sourcegraph-indexserver/merge.go:32-42, 180-236`; `main.go:1455-1456`).

(e) Statistics. None (set membership).

(f) Bounds. One goroutine per shard, so shard count is both parallelism and fan-out (`design.md:153-156`); delta shards add fan-out linearly until the 150 cap.

Lesson. zoekt rebuilds whole shards because a repo rebuild is cheap. Its delta-shard experiment is exactly "segment per refresh with tombstones in the base", and its authors name the missing piece: a merge policy. Without one the only bound is "rebuild after N deltas".

## 8. Vector indexes: pgvector and sqlite-vec

pgvector HNSW inserts are incremental by construction: each insert takes a shared page lock (exclusive only when the entry point may change), finds neighbours and splices the element into the on-disk graph under generic WAL (`src/hnswinsert.c:695-740`). Deletes are heap-driven: `hnswbulkdelete` repairs neighbour lists that point at dead elements, waits for in-flight inserts, then marks elements deleted (`src/hnswvacuum.c:376-395, 592-612`); the README warns vacuum "can take a while" and suggests reindexing first (`README.md:744-747`). IVFFlat inserts append to the nearest list by comparing against every centroid (`src/ivfinsert.c:20-70`); centroids are never retrained, so a drifting corpus degrades recall until a rebuild, which is why the README says to build the index after loading data (`README.md:307, 696`). sqlite-vec stores vectors in fixed-size chunks with a validity bitmap; insert takes the first free bit, delete clears it and zeroes the slot, and KNN scans every chunk (`sqlite-vec.c:4631-4680, 8685-8770, 8891-8899, 9880-9900`; `ARCHITECTURE.md:10-35`).

Lesson. A flat or graph vector index has no segment problem; it is a set of rows plus, for HNSW, a repair step on delete. vfs's vector leg is already this: chunk rows carry vectors, `select_unembedded` is the delta, and content-hash carry-forward is the dedupe. The only freshness gap is "chunk has no vector yet", and closing it costs embedding compute, not index maintenance.

## 9. Synthesis for vfs

### What maps onto a table of blobs with a verifying reader

Every system above holds the same four pieces: an immutable base, a small newer generation, a way to make the old copy of an updated document invisible, and a merge that folds generations together under a count or size budget. vfs already has three of the four. The base is the epoch. The newest generation is the scan tier, which is GIN's pending list and VectorChord's tape: linear in dirty rows, charged per call, correct by construction. Invisibility of stale copies is free for grep, because verification against live content rejects a stale posting the way GIN relies on heap visibility and pg_search on the heap fetch. What vfs lacks is the middle: a generation between "live rows" and "the epoch".

The segment pattern maps directly onto the existing key. A delta is a set of posting rows under a new epoch number that covers only the dirty entries, built from the dirty set alone, so its memory and CPU are bounded by the dirty set as the brief requires. Readers that today fetch `WHERE epoch = ? AND gram_key IN (...)` would fetch the same grams across the live set of epochs and union the decoded postings per gram before intersecting; Lucene and FTS5 do nothing more than this union. The `encoded` flag already partitions index tier from scan tier; the generalisation Lucene's live-docs and zoekt's tombstones suggest is that the flag names *which* generation owns the entry, so an entry re-posted in a newer delta is not also admitted from the base. For grep that ownership is optional, since verification catches the duplicate; for BM25 it is not, because a stale posting carries a stale `tf` and would score twice.

Statistics are where the prior art splits three ways, and vfs can pick its drift. Lucene, tantivy and pg_textsearch sum `df` and `N` across generations and let deleted-but-unmerged documents over-count until merge. FTS5 keeps `N` and `avgdl` exact by touching a totals row on every write, which vfs's write path forbids. VectorChord freezes everything and scores new terms at zero, which is the one option the field shows to be wrong. The brief's numbers bound the summed-stats drift tightly: at most 5 % of entries change per day, so between two rebuilds four hours apart at most about 2.5 % of entries are re-posted and double-counted in `df` and `N`. An idf of `log(1 + (N - df + 0.5)/(df + 0.5))` moves by a fraction of a percent under that. vfs's `OVERLAY_BUDGET` of 500 is the real statistics problem today: with 1 250 to 6 250 dirty entries in an hour, the lexical leg silently drops most of them. A delta generation built every few minutes keeps the scan tier under that budget almost always, which is the strongest argument for the segment pattern that the prior art offers.

### What each cadence looks like

Rebuilds run at 08:00, 12:00 and 16:00; the gaps are four hours, four hours and sixteen hours overnight, but the brief concentrates edits in the eight-hour day, so a refresh that finds no dirty rows writes no delta. Count only the daytime gaps.

| cadence | dirty entries per delta (brief) | deltas per 4 h gap, no merging | live generations with factor-8 tiers | with factor-4 tiers |
|---|---|---|---|---|
| 5 min | 100–500 | 48 | at most 7 small + 6 merged, about 9 typical | at most 3 + 3 + 1, about 7 |
| 15 min | 300–1 500 | 16 | at most 7 + 2, about 5 | at most 3 + 3 + 1, about 5 |
| 30 min | 600–3 000 | 8 | 8, one tier, no merge needed | at most 3 + 2, about 4 |
| 60 min | 1 250–6 250 | 4 | 4, no merge needed | 4, no merge needed |

The factor-8 column is Lucene's `segsPerTier`, tantivy's `min_num_segments` and pg_textsearch's `segments_per_level`; the factor-4 column is FTS5's `automerge`. The arithmetic is the same in all of them: `S` deltas collapse to about `factor × log_factor(S)` live generations, and each posting is rewritten once per tier it climbs, so two or three times across a four-hour gap rather than once per refresh. Without tiering, the alternative of folding every refresh into one running delta rewrites a growing blob set 48 times and approaches a quadratic amount of posting bytes; zoekt's 150-shard cap is the cost of having no tiering at all. At 30 and 60 minutes the gap holds too few deltas to need any merge, and the base rebuild is the compaction. At 5 and 15 minutes a merge step is what makes the cadence safe, and the full rebuild three times a day is the `optimize` that every system here also offers.

### Pitfalls the field has already paid for

Read fan-out across small generations. Lucene's 16 MB floor exists to stop "a long tail of small segments" (`TieredMergePolicy.java:162-166`); GIN charges the whole pending list as startup cost; zoekt's delta shards grow fan-out until a forced rebuild. vfs has a sharper edge: the posting fetch is an `IN` list of grams, and `S` generations multiply the rows by `S` and either the binds or the round trips against Oracle's 1 000-element cap. Twenty grams across 48 generations is 960 binds; `chunked()` keeps it legal, but the latency shows. Tiering, or a fetch shape planned against `membership_budget` for both epochs and grams, is not optional at five minutes.

Statistics drift. Lucene documents the direction of its error and accepts it; VectorChord shows the failure of freezing instead. The drift is bounded by the dirty fraction and reset by every full rebuild, so it is small here, but it belongs in a docstring the way the whole-corpus memory profile does today.

Ghost postings. A stale posting is harmless for grep because verification rejects it and the content fetch drops deleted entries. It is not harmless for BM25 unless the reader knows which generation owns each entry; Lucene's live-docs, FTS5's delete markers and zoekt's `FileTombstones` exist to answer that question before scoring.

Compaction storms and foreground stalls. Lucene warns that an aggressive deletes threshold merges "nearly all segments" continuously. GIN and pg_textsearch both kept a synchronous backstop because a schedule cannot save a level that is already full, and both made it yield to a rival merger. pg_textsearch's "one bounded pass per invocation" and FTS5's resumable page budget are the shapes that keep a merge from monopolising the lease: do a bounded amount of merge work per tick and leave the rest, so the 5-minute job never runs for six.

The dirty probe. Unchanged from `studies/2026-08-17-overlay-probe-index/SURVEY.md`: the `NOT encoded` probe must stay a literal predicate on Postgres, SQL Server and SQLite, and Oracle needs the function-based NULL trick. A five-minute refresh exercises it far more often than three rebuilds a day do.

### One-line version

The field agrees on immutable generations, overlay-style deletes, summed statistics and tiered merging under a count budget with a synchronous backstop; vfs already has the base, the overlay and the verifying reader, so the gap between rebuilds is a delta generation built from the dirty set, a merge step that keeps live generations near `factor × log(S)`, and a reader that unions grams across generations and knows which generation owns each entry before it scores.
