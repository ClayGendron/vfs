# Study: how pg_search (ParadeDB) and Tantivy store, build and search a BM25 index — and what a portable-SQL epoch index can borrow

- **Study for**: [2026-08-26-bm25-storage-design.md](../../2026-08-26-bm25-storage-design.md)
  §2 (prior art) — the question is whether spec 130's relational index
  (one row per `(term, chunk)`, ~40 bytes per posting, ~1 B rows at
  10 M chunks) should move to the gram index's shape: one row per
  `(epoch, term, block)` holding a compressed posting blob, built by the
  Rust engine and scored client-side.
- **Date**: 2026-08-26
- **Sources** (reference checkouts read-only, cited by commit; nothing
  copied — see the Sources line at the end for licences):
  - `~/Git/Repos/paradedb` @ 7496549 (2026-08-26, AGPL-3.0) —
    `pg_search/src/**`, `tokenizers/src/**`, `docs/documentation/**`.
  - `~/Git/Repos/tantivy` @ cce9950 (2026-08-26, MIT, crate version
    0.27.0) — `src/postings/**`, `src/fieldnorm/**`, `src/positions/**`,
    `src/query/bm25.rs`, `src/query/boolean_query/block_wand_*.rs`,
    `src/collector/**`, `src/indexer/**`.
- **Method**: read and grep only; three parallel sweeps over pg_search
  (block storage; build/insert/merge; query/tokenizers/docs) and one
  over Tantivy, cross-checked against each other. Every claim carries
  a `path:line` citation at the commit above. Where the code does not
  answer a question the memo says so.
- **One caveat up front**: pg_search does **not** build against the
  upstream Tantivy studied here. Its workspace pins
  `github.com/paradedb/tantivy` at rev `c3caae3f` with a `paradedb`
  feature (`Cargo.toml:69-72`), and several APIs it calls
  (`Bm25Params`, `SharedThreshold`, `PruningScorer`,
  `TopDocs::order_by::<Score>`) exist only in that fork. The posting
  format, skip index, fieldnorm code and block-WAND algorithm are
  upstream Tantivy's and are what the fork inherits; the fork was not
  cloned, so fork-only behaviour is described from pg_search's call
  sites, not from the fork's source.

## 1. The block-storage layer: Tantivy segment files on Postgres pages

**Unit of storage is the ordinary 8 KB Postgres page**, `PageInit`'d
with a special area holding `{next_blockno, xmax}`
(`pg_search/src/postgres/storage/block.rs:49-52`,
`buffer.rs:336-348`). Usable bytes per page are `BLCKSZ` minus the
special area and the page header — 8192 − 8 − 24 = **8160 bytes**,
computed by `bm25_max_free_space()` (`block.rs:943-949`), not a
literal. Two page styles share the header: *byte pages* where raw
bytes fill the free region and `pd_lower` moves
(`linked_bytes.rs:165-171`), and *item pages* using normal line
pointers for small records (`buffer.rs:616-636`).

**Block 0 is the metapage** (`metadata.rs:99`). It holds block numbers
for everything else — the segment-meta list, the schema and settings
blobs, the merge-lock and cleanup-lock pages, the vacuum list, the
free-space map — all allocated at build time (`metadata.rs:36-88,
102-135`); only legacy indexes use fixed slots 1/2/4/6
(`metadata.rs:305-308`).

**A segment file is a `LinkedBytesList`.** Every Tantivy component
(`.idx`, `.pos`, `.term`, `.fieldnorm`, `.fast`, `.del`, `.vec`) is one
header page (`LinkedListData {start_blockno, last_blockno,
blocklist_start}`, `block.rs:61-74`) plus a singly linked chain of full
byte pages joined by `next_blockno` (`linked_bytes.rs:77-104`). The
writer wraps Tantivy's `open_write` in a `BufWriter` sized
8160 × 64 ≈ 510 KB so relation extension happens 64 pages at a time
(`index/directory/mvcc.rs:55-58, 863-865`;
`MAX_BUFFERS_TO_EXTEND_BY = 64`, `storage/utils.rs:26`). Two details
matter for vfs:

- **The doc store is never persisted.** `.store`/`.tempstore` get a
  dummy `FileEntry` and the bytes are dropped
  (`index/writer/segment_component.rs:35-49, 56-65`); documents are
  re-read from the heap. The index holds postings, dictionary,
  fieldnorms and fast fields only — the same division vfs has, where
  `chunks.content` is the store.
- **Random reads need an offset→block map.** Tantivy's
  `FileHandle::read_bytes(range)` (`index/reader/segment_component.rs:52-77`)
  computes `ord = offset / 8160`, `local = offset % 8160`
  (`linked_bytes.rs:376-378, 415-419`) and looks the block number up in
  a **blocklist**: a second small chain of pages holding the ordered
  data-block numbers, bit-packed with the `bitpacking` crate in 32/128/
  256-element chunks (`blocklist.rs:19-28, 197-281`), decompressed
  once per file handle into a `Vec<BlockNumber>` (`blocklist.rs:379-503`).
  A single-page read is a zero-copy slice over the pinned page; a
  multi-page read copies (`linked_bytes.rs:410-448`).

**Caching is Postgres shared buffers**, not a private cache. Each open
file keeps a 16-entry LRU (`BLOCK_CACHE_SIZE = 16`,
`linked_bytes.rs:37`) of pages that were share-locked, unlocked, and
**kept pinned** (`buffer.rs:252-261, 1099-1117`); pins drop on
eviction. So a posting-list read is page-granular buffer-manager
traffic with no extra copy for in-page slices.

**Segment metadata and visibility.** The live segment list is a
`LinkedItemList<SegmentMetaEntry>` of item pages (`metadata.rs:364-371`,
`linked_items.rs:32-59`). An entry is `{segment_id, max_doc, tag
(Mutable|Immutable), xmax}` plus per-component `FileEntry{starting_block,
total_bytes}` and an optional `DeleteEntry{file_entry, num_deleted_docs}`
(`block.rs:217-242, 276-287`). Visibility is **not** snapshot-based:
`xmax` is `Invalid` (live) or `Frozen` (merged away), and `visible()` is
just "not deleted" (`block.rs:909-912`). What protects a reader is a
**pin** on each chosen segment's first block, collected in a
`PinCushion` (`index/directory/utils.rs:414`, `mvcc.rs:868-885`); a
dead segment is `recyclable()` only when a conditional cleanup lock on
that block succeeds, i.e. no reader holds it (`block.rs:914-940`).
List mutation is copy-on-write: `atomically()` takes an exclusive lock
on the header page, copies every item page to fresh blocks, applies
the change, then swaps `start_blockno` and files the old pages for
recycling keyed by `ReadNextFullTransactionId()`
(`linked_items.rs:562-633, 661-720`). This is an epoch pointer-swap
with a pin-based grace period — structurally the same publish
discipline as vfs's `publish_epoch` / `reclaim_epochs`, done with
buffer pins instead of an epoch column.

**Free space** is a custom FSM: an AVL tree on the root page maps
`FullTransactionId → freelist head` (`fsm.rs:634-720`), freelists are
pages of `(8160 − 4)/4` block numbers (`fsm.rs:702-703`), and `drain`
takes the greatest key ≤ the current xid (`fsm.rs:767-870`). Vacuum
cleanup is simply a merge pass (`vacuum.rs:24-31`).

**Locking.** No heavyweight relation lock beyond what the AM entry
point already holds (`rel.rs:194-213`); coordination is buffer locks
on dedicated pages plus advisory locks. The *merge lock* (exclusive
buffer lock on its page, `storage/merge.rs:41-67`) is held only while
choosing candidates and writing a `MergeEntry{pid, xmin, segment ids}`,
then released so disjoint merges run concurrently
(`postgres/merge.rs:479-519`). Readers **pin** the *cleanup-lock*
page for the life of a reader (`index/reader/index.rs:501`); merges
hold it shared; `ambulkdelete` takes it exclusive to wait out merges
and then `LockBufferForCleanup` to wait out reader pins
(`delete.rs:104-136, 271-282`). Readers never block writers at the
relation level; the contention points are the list-header share lock
during traversal (`linked_items.rs:164-201`) and pins delaying
recycling.

**WAL is generic WAL and full-page images; there is no custom redo of
Tantivy bytes.** A mutable buffer picks its `XlogStyle` from
`RelationNeedsWAL` (`rel.rs:471-521`): existing pages go through
`GenericXLogRegisterBuffer` on first `page_mut()` and
`GenericXLogFinish` on drop (`xlog.rs:78-95, 116-118`); brand-new pages
use `MarkBufferDirty` + `log_newpage_buffer` (`xlog.rs:105-110`). Page
ordering is deliberate so a replaying standby never sees a dangling
`next_blockno` (`linked_items.rs:376-416`). The registered custom
resource manager (`RMGR_ID = 137`, `custom_rmgr.rs:22-23`) carries one
record type, emitted at the end of `ambuild`, whose redo does nothing
but refuse on a standby (`custom_rmgr.rs:25-37, 67-77`; replicas are
gated to the Enterprise build, `metadata.rs:138-146`). A `deferred_wal`
feature turns WAL off during the build and `log_newpage_range`s the
whole relation afterwards (`build.rs:48-55, 92-103`).

**Deletes.** A heap delete/update does not touch the index. `ambulkdelete`
iterates each segment's `ctid` fast field over `0..max_doc`, asks
Postgres' callback whether each ctid is dead, queues Tantivy
`DeleteOperation::ByAddress`, and writes a **new `.del` alive-bitset
file** for the same segment; the meta entry's `DeleteEntry` is swapped
and the old `.del` becomes a recyclable orphan (`delete.rs:152-239,
338-376`; `index/directory/utils.rs:115-121, 175-206`). Query-time
visibility is a **heap check**, not an index check — §5.

## 2. Tantivy's posting format

**Block size is 128.** `COMPRESSION_BLOCK_SIZE = BitPacker4x::BLOCK_LEN`
(`src/postings/compression/mod.rs:3`), the `bitpacking` crate's
SSE-width packer (`Cargo.toml:61`); the positions module states the
number in prose ("blocks of 128 deltas", `src/positions/mod.rs:11-13`).

**Per term, the `.idx` bytes are:** an optional skip section, then the
posting blocks (`src/postings/serializer.rs:471-476`):

- *Doc ids*: each full block of 128 ids is delta-coded against the
  previous block's last id and bit-packed with
  `compress_strictly_sorted` (deltas ≥ 1, so a dense run costs 0 bits
  per doc; `compression/mod.rs:36-46`, `serializer.rs:379-390`). The
  block's bit width is recorded in the skip entry, not in the block.
- *Term frequencies*: a second bit-packed block of 128 values,
  **minus-one encoded** (tf ≥ 1 is stored as tf − 1, so an all-ones
  block costs 0 bits; `compression/mod.rs:48-76`,
  `serializer.rs:391-397`). Written only when the field records
  frequencies.
- *Tail*: the final partial block (df mod 128) is delta + variable-byte
  for ids and vint for tfs (`serializer.rs:449-470`). A term with
  df < 128 has **no skip section at all** (`serializer.rs:471`,
  `block_segment_postings.rs:82-83`).
- *Positions* live in `.pos`, per term, as bit-packed blocks of 128
  position deltas with the block bit widths stored up front and a vint
  tail; the reader stops when the byte range is exhausted
  (`src/positions/mod.rs:15-29`). The skip entry carries the block's
  tf sum so a seek can skip the right number of positions
  (`skip.rs:73-75, 236-239`).

**The skip index is one fixed-width entry per full block**, written
by `SkipSerializer` (`src/postings/skip.rs:55-90`) and read by
`SkipReader::read_block_info` (`skip.rs:205-253`):

| record option | bytes per block | fields |
|---|---|---|
| Basic | 5 | last doc id (u32), doc bit width + strict-delta flag (u8) |
| WithFreqs | 8 | + tf bit width (u8), **block-WAND fieldnorm id (u8), block-WAND max tf (u8)** |
| WithFreqsAndPositions | 12 | + tf sum (u32) before the two block-WAND bytes |

The two block-WAND bytes are the whole "block max" story. At
serialization the writer computes, for each block, the `(fieldnorm_id,
tf)` pair among its 128 docs that maximizes the BM25 tf-factor under
**that segment's** average field length (`serializer.rs:404-428`), and
stores the pair — the tf saturated to 255 (`skip.rs:31-43`). It does
*not* store a score: the score is re-derived at query time from the
pair with the query's `Bm25Weight` (`skip.rs:175-184`), which is why a
segment's block-max data stays valid when corpus statistics change
(§3 has the one caveat). The skip cost is therefore 8 bytes per 128
postings, ~0.06 bytes per posting.

**The term dictionary is an FST** (`tantivy-fst`) mapping each term to
its ordinal, plus a separate `TermInfoStore`
(`src/termdict/mod.rs:1-19`; the `quickwit` feature swaps in an
SSTable dictionary, `termdict/mod.rs:21-29`). **Per-term df lives in
`TermInfo`** — `{doc_freq: u32, postings_range, positions_range}`
(`src/postings/term_info.rs:9-16`) — which is bit-packed in blocks of
256 ordinals with the first entry of each block uncompressed and the
rest delta-coded (`fst_termdict/term_info_store.rs:12, 138-155`;
`term_info.rs:32-38`). `doc_freq` counts the segment's postings
*including* docs since deleted (nothing rewrites `.idx` on delete).

**Doc ids are dense per segment** (`0..max_doc`), which is what makes
the fieldnorm array positional (§3) and the deltas small.

## 3. Corpus statistics across segments, deletes, and fieldnorms

**N and average length are summed over segments at query time**, via
the `Bm25StatisticsProvider` trait that `Searcher` implements
(`src/query/bm25.rs:15-50`):

- `total_num_tokens(field)` = Σ per segment of a **u64 written at the
  head of the field's `.idx` data** at serialization
  (`serializer.rs:128`; read back in
  `src/index/inverted_index_reader.rs:72-73, 251-252`), counted one per
  token as the writer subscribes it (`postings_writer.rs:215`).
- `total_num_docs()` = Σ `segment_reader.max_doc()` — the high-water
  mark, **not** the alive count (`bm25.rs:38-45`;
  `segment_reader.rs:58-66` distinguishes `max_doc` from `num_docs`).
- `doc_freq(term)` = Σ per segment `TermInfo.doc_freq`
  (`src/core/searcher.rs:132-140`, `inverted_index_reader.rs:276-281`).
- `avg_fieldnorm = total_num_tokens / total_num_docs` (`bm25.rs:109-111`).

**Deletes therefore do not change any statistic until a merge
rewrites the segment.** The `.del` file is an alive bitset consulted
by scorers (`segment_reader.rs:178-179, 435`), and the merger iterates
`doc_ids_alive()` to build the new segment (`src/indexer/merger.rs:70-131,
1581, 1606`), at which point the new segment's header token count,
`max_doc` and per-term df are recomputed from survivors. Upstream
Tantivy's `LogMergePolicy` will merge purely on deletes only when
`del_docs_ratio_before_merge` says so — default 1.0, i.e. never
(`src/indexer/log_merge_policy.rs:15`). pg_search (§4) inherits the
same drift: its own bookkeeping has no `total_num_tokens` or average
length at all (grep of `pg_search/src` finds only fieldnorm option
plumbing); it summarizes segments as `max_doc − num_deleted_docs` for
planner estimates (`storage/block.rs:568-586`) and relies on Tantivy for
idf/avgdl. Its `LazyWeight` builds **one weight per query** and shares
it across segments precisely because `doc_freq` walks every segment's
dictionary (`index/reader/scorer.rs:23-55`).

**Fieldnorms are one byte per document per field**, a positional
`Vec<u8>` indexed by doc id (`src/fieldnorm/writer.rs:9-13, 74-83`),
quantized "using the exact same scheme as Lucene" (`fieldnorm/mod.rs:9-18`)
through a 256-entry monotone table: exact from 0 to 40, then steps of
2, 4, 8, 16 … up to 2 013 265 944 (`fieldnorm/code.rs:13-268`);
`fieldnorm_to_id` rounds **down** (`code.rs:7-11`), so the stored
length is ≤ the true length (`reader.rs:107-116`). The payoff is the
BM25 cache: `Bm25Weight` precomputes `k1·(1 − b + b·dl/avgdl)` for all
256 ids once per query (`bm25.rs:58-69`), so scoring a posting is one
table lookup, one division (`bm25.rs:188-193`). For vfs, whose `dl` is
exact per chunk and whose chunks are bounded, the id table above 40
would cost a little precision on long chunks; spec 130's fidelity
referee would show whether the top-10 moves.

**The one caveat on block-max across segments** is stated in the
scorer: the stored pair maximizes the tf-factor under the *segment's*
average length; with a different corpus-wide average the argmax could
in theory be a different doc, so the block max may be slightly low —
"guaranteed to be correct if there is only one segment"
(`src/query/term_query/term_scorer.rs:58-70`). An epoch-rebuilt vfs
index is exactly that one-segment case.

## 4. Build path for a large table; incremental writes; merge policy

**CREATE INDEX** (`pg_search/src/postgres/build.rs:38`, `build_parallel.rs:664`):

- A Postgres **parallel heap scan** — the leader initializes a
  `ParallelTableScanDesc` in DSM (`build_parallel.rs:150-156`), each
  worker runs `table_index_build_scan` with a per-tuple callback
  (`build_parallel.rs:237, 320-332, 583`), `SnapshotAny` for a plain
  build (`build_parallel.rs:682-688`). Progress reaches
  `pg_stat_progress_create_index` every 5 tuples (`build_parallel.rs:57`).
- **Memory = `maintenance_work_mem` divided evenly across workers**
  (leader included), each share clamped to Tantivy's `[15 MB, 1 GiB)`
  — the floor is `MEMORY_BUDGET_NUM_BYTES_MIN = 15 × 1 000 000`
  (`gucs.rs:792-828`; upstream `src/indexer/index_writer.rs:29-33`);
  under 15 MB per worker the build ERRORs. The cap's comment: no
  throughput gain past ~1 GB (`gucs.rs:797-799`). Each worker owns a
  single-threaded `SerialIndexWriter` (`index/writer/index.rs:196-198`)
  and **flushes a segment when the arena reaches the budget** or a
  per-worker doc cap (`writer/index.rs:368-396`); every flushed segment
  is published into the meta list immediately (`writer/index.rs:457-490`).
- **Workers**: `parallel_workers` reloption, else
  `max_parallel_maintenance_workers`, capped by the global worker GUCs
  and by `ceil(target_segment_count / 2)` so each worker merges at least
  twice and reuses freed blocks (`build_parallel.rs:815-891`); a WARNING
  fires below 3. Launch failure falls back to a serial build
  (`build_parallel.rs:785-798`).
- **Target segment count** = `target_segment_count` reloption, default
  `available_parallelism().max(4)` (`options.rs:53-56, 450-460`,
  `lib.rs:108-116`), overridable by `paradedb.global_target_segment_count`
  (`gucs.rs:459-468`); collapses to 1 when the heap is ≤ 15 MiB or has
  fewer rows than the target (`build_parallel.rs:897-921`).
- **Per-worker merging, no global merge.** Each worker is assigned a
  share of the target (`build_parallel.rs:293-296`) and after each
  flush merges its own smallest segments toward that share
  (`build_parallel.rs:490-579`); at commit it solves for the exact
  count (`build_parallel.rs:467-535`). The leader only sums counts
  (`build_parallel.rs:776-781`). Tests expect exactly 4 segments for a
  target of 4 (`build_parallel.rs:1051-1067`). A `DiskSpaceGuard`
  extrapolates from the first flushed segment and aborts at 98 % of
  tablespace free space (`writer/index.rs:112-185`).
- `build_partitioning.rs` is the `partition_by` reloption (a k-d tree of
  sampled value boundaries shared through DSM so every worker cuts
  identically, `build_partitioning.rs:18-95`), not a heap split.

**Incremental INSERT/UPDATE — a two-tier LSM** (`docs/welcome/architecture.mdx:22, 42-46`):

- **Mutable segment = a ctid log, not a Tantivy segment.** With
  `mutable_segment_rows` > 0 (default 1000, max 10 000, `options.rs:73-74,
  1105-1113`), `aminsert` buffers ctids and, at **statement** end
  (`aminsertcleanup` on PG17+, a hook polyfill on 15/16,
  `insert.rs:201-220`, `fake_aminsertcleanup.rs:18-34`), appends
  `Add(ctid)` items to the current unfrozen mutable segment
  (`insert.rs:411-448`; `storage/block.rs:149-152, 245-274`). A reader
  **materializes it on open by re-fetching the ctids from the heap and
  indexing them into a `RamDirectory`** (`index/directory/mvcc.rs:414-438,
  887-960`) — which is why the docs warn that larger values cost read
  latency and RAM (`docs/documentation/performance-tuning/writes.mdx:46-57`).
  It freezes at the row threshold and becomes mergeable
  (`storage/block.rs:443-466, 597-609`).
- **Immutable path** (feature off, or a statement larger than the
  threshold): a `SerialIndexWriter` with `work_mem` clamped to
  `[15 MB, 1 GiB)` (`insert.rs:49`, `gucs.rs:834-855`) produces
  ⌈bytes / work_mem⌉ real segments per statement, flushed at cleanup
  (`insert.rs:324-337, 404-409`). So **a small transaction produces
  one segment or one log append; there is no per-transaction segment
  by default** — the memtable is the ctid log.
- After cleanup the backend calls `do_merge(MergeStyle::Insert)`
  (`insert.rs:376-401`).

**DELETE/UPDATE**: no hook; stale ctids live until VACUUM writes `.del`
bitsets (§1). Vacuum cleanup then merges (`vacuum.rs:24-31`).

**Merge policy — "layer sizes"** (`index/merge_policy.rs:176-340`;
`postgres/merge.rs:156-335`):

- Two reloptions parsed with `pg_size_bytes`: `layer_sizes` (foreground,
  **default empty**) and `background_layer_sizes` (default **100 KB,
  1 MB, 10 MB, 100 MB, 1 000 MB, 10 000 MB**, `options.rs:61-71`; the
  docs list five and omit 10 MB, `writes.mdx:12-17`).
  `paradedb.global_enable_background_merging` (default true) zeroes the
  background list when off (`gucs.rs:470-477`).
- Candidates: every mutable segment is a level-0 candidate by itself;
  then for each layer, largest first, segments are sorted by
  alive-adjusted size (`byte_size × live fraction`,
  `merge_policy.rs:356-373`), any single segment larger than the layer
  is skipped, and a candidate closes when its actual bytes reach
  `layer + layer/3` (`merge_policy.rs:252-292`); candidates under 2
  segments are dropped unless they are a mutable conversion
  (`merge_policy.rs:307-328`).
- **Steering toward the target count**: if visible segments ≤
  `target_segment_count`, no merging at all; otherwise background layers
  larger than `(index_bytes / target) × 2/3` are dropped
  (`postgres/merge.rs:156-231`).
- **Who runs it**: if background layers yield candidates and there is
  no backpressure, a dynamic background worker is launched
  (`postgres/merge.rs:305-311`; at most two per index, a small and a
  large slot split at `LARGE_MERGE_THRESHOLD = 100 MB`,
  `postgres/merge.rs:588-667`); on an insert with foreground layers or
  backpressure (> 2 mutable segments, `postgres/merge.rs:248-264`) the
  **inserting backend merges synchronously** with a fixed 15 MiB budget
  (`writer/index.rs:570-577`). Vacuum-style calls never merge in the
  foreground.
- Documented history: 0.15.9 introduced `layer_sizes` at
  100 KB/1 MB/100 MB; 0.17.0 moved the large layers to the background
  (`docs/changelog/0.15.9.mdx:19-23`, `docs/changelog/0.17.0.mdx:37-44`).

For contrast, upstream Tantivy's default `LogMergePolicy` merges by
log-bucketed doc count: `min_layer_size 10 000`, `level_log_size 0.75`,
`min_num_segments 8`, `max_docs_before_merge 10 000 000`
(`src/indexer/log_merge_policy.rs:8-11`), with `MAX_NUM_THREAD = 8`
indexing threads each owning a segment writer
(`src/indexer/index_writer.rs:36`).

## 5. Top-k: block-WAND in Tantivy, and how pg_search wraps it

**The algorithm** (`src/query/boolean_query/block_wand_union.rs:145-215`)
is Ding & Suel's BMW. Scorers are kept sorted by current doc;
`find_pivot_doc` accumulates each term's **global max score**
(`Bm25Weight::max_score()` = score at fieldnorm id 255 and tf 2⁶⁴-ish,
`bm25.rs:183-186`) until the running sum exceeds the threshold — the
first doc at which that happens is the pivot
(`block_wand_union.rs:16-43`). Then each scorer up to the pivot is
**shallow-advanced to the block containing the pivot** (skip entries
only, no decompression) and the **per-block maxima are summed**
(`:172-178`). If the sum ≤ threshold, the whole block range is skipped
by advancing one scorer past the smallest `last_doc_in_block`
(`:49-83`); otherwise the scorers are aligned on the pivot, the doc is
scored exactly, and if it beats the threshold the collector's callback
returns the new threshold (`:192-213`). A single-term query has a
~3× faster specialization that just hops blocks whose max ≤ threshold
(`:218-260`). Block max for a full block comes from the 2 skip bytes
(`block_segment_postings.rs:147-179`); for the vint tail it is
computed from the loaded block or falls back to the global max.

**Where the threshold comes from**: `TopNComputer` keeps a buffer of
2·k, and each time it fills, truncates to the median and publishes it
as the threshold; the comparison is strict, so a doc must *beat* it
(`src/collector/top_score_collector.rs:600-645`). `for_each_pruning` is
invoked per segment from `Score::MIN`
(`src/collector/sort_key/sort_by_score.rs:46-55`), so in upstream
Tantivy the threshold does **not** carry across segments.

**When block-WAND applies** (`src/query/boolean_query/boolean_weight.rs:581-612`):
the boolean weight must specialize to a pure **term union** (all
`Should` clauses are term scorers and the combiner sums — `dis_max`
falls back) or a pure **term intersection**; anything else runs the
generic pruning loop over a materialized scorer. So multi-term
disjunctions and conjunctions of plain terms prune; phrase, fuzzy,
regex, boosts and filters wrapping the terms do not.

**pg_search's wrapping.** `ORDER BY score LIMIT n` plans as
`ExecMethodType::TopK` (`customscan/builders/custom_path.rs:135-147`)
and the executor `TopKScanExecState` (`basescan/exec_methods/top_k.rs:58`;
`docs/documentation/sorting/topk.mdx:88-107`). Score-DESC uses the
fork's `TopDocs::order_by::<Score>` path, commented as the one that
"allows for Block-WAND" (`index/reader/index.rs:1481-1537`); score-ASC
wraps the score and is documented as slower and non-pruning
(`index.rs:1496-1514`). Three interactions matter for vfs:

- **Threshold shared across parallel workers.** pg_search adds what
  upstream lacks: a DSM `ParallelScanThresholdState` with a lock-free
  `AtomicU64` packing `(ordered f32 score, !segment_ord)` updated by
  CAS, implementing the fork's `SharedThreshold`
  (`postgres/shared_threshold.rs:6-18, 138-170, 204-250`), wired into
  the collector only for parallel scans (`index.rs:1091-1097, 1519-1525`).
  Streaming scans also raise a monotone threshold as results are
  emitted (`scan/batch_scanner.rs:335-357`).
- **The planner only trusts pruning for a single posting list.**
  `is_topk_prunable()` is true for a bare term, a `Match` that
  tokenizes to ≤ 1 term, or a one-term parser string; boosts,
  const-scores, score filters and heap filters "build their own
  non-pruning weight" (`query/mod.rs:557-624`); `decide_scan_parallelism`
  then forces a serial scan (`basescan/cost.rs:196-227, 367-374`).
  Multi-term queries still use the collector but the planner does not
  assume sublinearity.
- **Filters and visibility.** Predicates on **columnar ("fast") fields**
  — every non-text, non-JSON field by default, text via
  `columnar=true` or `literal` (`docs/documentation/indexing/columnar.mdx:7-10,
  85-91, 182-200`) — are rewritten into the Tantivy query
  (`docs/documentation/filtering.mdx:22-82`; `qual_inspect.rs:959-967`).
  Anything else becomes a `HeapFilterQuery` whose scorer wraps the
  indexed query, reads the `ctid` fast field, **fetches the heap tuple
  for each candidate and runs `ExecEvalExpr`** — inside the DocSet,
  before collection, scores unchanged (`query/heap_field_filter.rs:64-200`;
  `fast_fields_helper.rs:222-224`). Heap MVCC is a separate pass:
  every surviving ctid goes through `VisibilityChecker` (visibility
  map fast path, then `heap_hot_search_buffer`, `postgres/heap.rs:60-345`),
  and if fewer than `limit` survive the executor **re-queries with a
  larger chunk** — initial fetch `limit × (1 + (1+dead)/(1+live)) ×
  paradedb.limit_fetch_multiplier`, growing by
  `paradedb.topk_retry_scale_factor` (default 2) to
  `paradedb.max_topk_chunk_size` (default 100 000)
  (`top_k.rs:97-114, 540-556`; `gucs.rs:68-74`). Docs tie this to
  `Heap Fetches` in EXPLAIN and say scores can be skewed by dead rows
  until VACUUM (`performance-tuning/reads.mdx:33-48`;
  `sorting/score.mdx:264-275`).
- Deleted docs are skipped by the alive bitset during scoring
  (`index/reader/scorer.rs:161-190`), so they never enter the top-k
  buffer even though they still count in N and df (§3).

**Custom scoring**: none. `index/reader/scorer.rs` only wraps weights
and pruning; scores are the fork's Tantivy BM25.

## 6. The BM25 formula and its exactness versus Lucene

Upstream Tantivy (`src/query/bm25.rs`):

- `K1 = 1.2`, `B = 0.75` as constants (`bm25.rs:8-9`).
- `idf = ln(1 + (N − df + 0.5) / (df + 0.5))` — Lucene's smoothed,
  never-negative form (`bm25.rs:52-56`).
- `weight = idf × (1 + K1)` — **the `(k1+1)` factor is retained**
  (`bm25.rs:158-160`), and the tf factor is `tf / (tf + K1·(1 − B +
  B·dl/avgdl))` (`bm25.rs:58-60, 188-193`), so a single-term score is
  `idf · (k1+1) · tf / (tf + norm)` — exactly spec 130's
  `lexical.py:141-142`. The `explain` tree literally credits Lucene's
  format (`bm25.rs:195-226`).
- `dl` is the **quantized** fieldnorm (§3) and `avgdl` is
  `total_num_tokens / max_doc` summed over segments, so two things
  differ from vfs's tables: length precision above 40 tokens, and N
  counting deleted docs until merge.

pg_search exposes k1/b **per field** in its fork: typmod options
validated to `k1 ∈ [0, 100]`, `b ∈ [0, 1]`
(`api/tokenizers/typmod/validation.rs:279-291`), applied through the
fork's `Bm25Params` (`schema/config.rs:317-323`; changelog
`docs/changelog/0.23.0.mdx:19`). There is no user-docs page for them.
`fieldnorms` defaults to true except for the literal tokenizers
(`api/tokenizers/mod.rs:325-338`).

## 7. Tokenizers for code and identifiers

**Configuration surface.** A tokenizer is a Postgres type cast on the
indexed expression — `(col::pdb.ngram(3,3))`, options as string
arguments such as `pdb.simple('stemmer=english', 'ascii_folding=true')`
(`docs/documentation/tokenizers/overview.mdx:18-23`;
`token-filters/overview.mdx:7-12`); a cast to `::text[]` previews the
tokens (`overview.mdx:8-14`). Index-level `WITH (key_field, search_tokenizer,
target_segment_count, layer_sizes, mutable_segment_rows, …)`. A legacy
JSON config function `paradedb.tokenizer(...)` with `remove_long
DEFAULT 255` still exists (`api/config.rs:64-79`); the typmod path
applies no length filter unless asked (`api/tokenizers/typmod/mod.rs:376-379`).
Extra casts with `alias=` index the same column several ways
(`tokenizers/multiple-per-field.mdx:6-50`); `search_tokenizer` (index
option or a per-query cast) applies a different tokenizer at query
time (`tokenizers/search-tokenizer.mdx:12-61`).

**The list** (`tokenizers/src/manager.rs:348-424`): `unicode_words`
(default; UAX #29 boundaries, lowercased), `simple` (split on
non-alphanumeric), `whitespace`, `icu`, `literal` (= `keyword`; the raw
string, no filters, no lowercasing), `literal_normalized`,
`regex_pattern`, `chinese_compatible`, `lindera`, `jieba`, `ngram`,
`edge_ngram`, and **`source_code`**.

**`source_code`** (`tokenizers/src/code.rs`, whose header says it was
taken from Quickwit) is a character-class state machine over
Upper/Lower/Numeric/Delimiter (`code.rs:229-252`) that cuts at every
delimiter, every class change, and every Upper→Lower transition unless
the upper case letter starts the run: `PigCaféFactory2` →
`Pig, Café, Factory, 2`; `TPigCafeFactory` → `T, Pig, Cafe, Factory`;
`PIG_CAFE_FACTORY` → `PIG, CAFE, FACTORY` (tests `code.rs:255-394`).
Lowercase and ASCII folding are applied by default
(`manager.rs:615-622`). Two differences from spec 130's tokenizer:
**it does not also emit the whole identifier**, and it does not drop
one-character parts — so `pthread_create` is searchable as `pthread`
and `create` but not as `pthread_create`, whereas vfs emits all three.
There is no digit-led special case; `0x1f` splits at the class change.

**`ngram(min, max, 'prefix_only=…', 'positions=…')`** emits every gram
size in `[min, max]`; positions are all 0 (no phrase queries) unless
`min == max` and `positions=true`, in which case a phrase query over
fixed grams gives exact-substring matching
(`available-tokenizers/ngrams.mdx:4-39`; `tokenizers/src/ngram.rs:17-21`).
**`edge_ngram(min, max, 'token_chars=…')`** emits word prefixes with
Unicode-category character classes (`edge-ngrams.mdx:4-26`; added in
0.23.0). **Filters**, applied in a fixed order — length (bytes) →
trim → lowercase → Snowball stemmer (20 languages) → custom stopwords
→ ASCII folding → alphanumeric-only → per-language stopwords
(`manager.rs:306-326`; `token-filters/stemming.mdx:11`,
`stopwords.mdx:11-16`). `literal` accepts none.

## 8. Documented sizes, build times, and limits

What the docs and code state (nothing else was found):

- **Memory**: ≥ 15 MB per writer/worker is enforced
  (`performance-tuning/create-index.mdx` prose 16-19; `writes.mdx:20-21`);
  `maintenance_work_mem` "start at RAM/16, at least 64 MB per worker",
  PG's 64 MB default called conservative (`create-index.mdx:21-33`);
  `work_mem` suggested 64 MB (`writes.mdx:33-44`); Docker auto-tune:
  `maintenance_work_mem = RAM/16` capped at 2 GB, `work_mem = (RAM −
  shared_buffers)/(3 × max_connections)` min 15 MB
  (`performance-tuning/overview.mdx:27-38`).
- **Workers**: `max_parallel_maintenance_workers` rule of thumb CPUs/2,
  min 2, max 8 (`create-index.mdx:9-19`); `target_segment_count`
  defaults to the CPU count, "merely a suggestion", and should match
  `max_parallel_workers_per_gather` (`performance-tuning/reads.mdx:49-65,
  90-121`).
- **Segments**: layer defaults as in §4; `mutable_segment_rows` 1000,
  max 10 000; at most two background mergers per index; 100 MB
  small/large split (`postgres/merge.rs:592-598`).
- **Query**: Top-K ≤ 3 ORDER BY columns documented
  (`sorting/topk.mdx:192-195`), 5 in code (`index/reader/index.rs:66`);
  `paradedb.min_rows_per_worker` 300 000; retry factor 2; max top-k
  chunk 100 000; streaming batch cap 128 000 (`scan/batch_scanner.rs:37`).
- **Schema**: 32 index columns (Postgres), more via a composite `ROW()`
  cast (`indexing/indexing-composite.mdx:6-23`); one ParadeDB index per
  table (`build.rs:68-79`); k1/b ranges as in §6. Token length: no
  default cap on the typmod path; upstream Tantivy drops tokens over
  `u16::MAX − 5` bytes (`src/tokenizer/mod.rs:174`).
- **Autovacuum**: recommended at least every ~100 000 single-row
  updates because dead ctids inflate heap fetches and skew scores
  (`reads.mdx:47-48`).
- **Performance claims** exist only as relative changelog figures
  (e.g. "~5× indexing time and ~20× write throughput" in 0.14.0,
  `docs/changelog/0.14.0.mdx:12-13`; "10-15× INSERT/UPDATE" in 0.15.6).
- **Not documented anywhere**: index-bytes-to-heap ratios, absolute
  build times or QPS, a segment-count or corpus-size ceiling, fast-field
  cardinality limits. `benchmarks/README.md` and
  `DATASET_PREPARATION.md` describe the harness (stackoverflow and
  cohere datasets at 10 k/100 k/1 M rows, 3-run windows) and publish no
  results.

## 9. What a portable-SQL epoch index can borrow, and what needs an index AM

The two systems agree on a division of labour that maps onto vfs
cleanly: **the engine's pages hold opaque, self-describing byte
blocks; the search logic runs above them**. pg_search's storage layer
is 8160-byte chunks in a linked chain with an offset→block array; vfs's
analogue is a row per `(epoch, key, block_no)` whose blob the B-tree
locates by key. Neither needs the engine to understand postings. What
follows is organized by what vfs can take structurally, given its
model — **one whole rebuild per reindex, one epoch = one segment, no
incremental merges, doc ids are `chunk_id` BIGINTs**.

### Borrow directly

1. **Block-per-row postings at 128 docs, delta + bit-packed ids and
   minus-one tfs.** A row `(epoch, term, block_no) → blob` with the
   block's ids and tfs in Tantivy's layout (§2) is the gram
   `posting_list` shape with a tf lane added. Cost arithmetic, derived
   not measured: a term at df/N = 1 % over 10 M chunks has mean id gap
   ~100 → ~7 bits per id, tf typically 1–3 bits, so **~1.0–1.5 bytes
   per posting plus ~0.06 bytes of skip metadata**, against 40 today
   (a ~30× reduction; the design memo's prototype benchmark owns the
   real number). Row count becomes Σ⌈df/128⌉ ≈ postings/128 for common
   terms plus one row per rare term — a few tens of millions of rows
   at 10 M chunks instead of ~1 B. Tantivy's choice to put the
   **partial tail block in vint** and to omit the skip section below
   df = 128 (`serializer.rs:449-476`) is worth keeping: most terms in
   a code vocabulary are rare and would otherwise pay a full 128-slot
   frame. The gram engine in `crates/vfs-core` already does delta +
   varint with a pure-Python twin; bit-packing is a codec upgrade to
   that engine, not a new subsystem.

2. **Per-block maxima as columns, not bytes — and exact, because the
   epoch is one segment.** Tantivy stores a `(fieldnorm_id, max_tf)`
   pair per block and re-scores it at query time because segment and
   corpus statistics differ (§2, §3). In vfs's epoch model N, avgdl and
   df are frozen for the epoch, so the block's **maximum BM25
   contribution is a scalar known at build time** and can sit in a
   `block_max REAL` column beside `last_doc BIGINT`. That does two
   things Tantivy cannot: the SQL fetch itself can be
   `WHERE epoch = ? AND term IN (…) AND block_max > ?` or
   `ORDER BY block_max DESC`, so **block skipping happens in the
   engine's B-tree before any blob is transferred** — the portable
   form of "shallow advance" — and the client-side WAND has an exact
   upper bound with none of the multi-segment slack the scorer warns
   about (`term_scorer.rs:63-70`). `find_pivot_doc`'s per-term global
   max is then simply `MAX(block_max)` per term, one more scalar per
   `lex_df` row.

3. **Statistics as one header row per epoch, and df per term.**
   Tantivy's per-segment header (`total_num_tokens`, `max_doc`) plus
   `TermInfo.doc_freq` (§3) is exactly `lex_stats` + `lex_df`; spec
   130 already has both. The one addition worth taking is Tantivy's
   habit of keeping **df and the posting byte range together**: a
   `lex_df` row that also carries `block_count` and `MAX(block_max)`
   lets the planner-side ladder (grep's `_posting_meta`) price a
   term's fetch before issuing it — the same rarest-first, budgeted
   fetch grep runs on grams.

4. **Quantized norms in a dense array, addressed by ordinal.** One
   byte per doc indexed by a dense doc ordinal (§3) is what makes
   Tantivy's scoring a table lookup. vfs's `chunk_id` is a sparse
   BIGINT, so the direct borrow needs a per-epoch **ordinal**
   assignment (`0..N`, in `chunk_id` order) recorded in `lex_docs`; the
   postings then delta-code ordinals (smaller gaps than sparse ids,
   and no gap inflation from deleted chunks), and the norm array is
   one blob per, say, 65 536 ordinals — 10 M chunks is ~10 MB, ~150
   rows. Whether to keep exact `dl` (spec 130's choice) or Lucene's
   256-step table is a fidelity question the referee can answer; the
   table lookup speed is the reason to quantize, not the byte.
   Precomputing `weight` per posting (spec 130's fork E3) is *not*
   worth carrying into blobs — a float per posting is 4 bytes against
   ~1.2 for `(id, tf)`; Tantivy's 256-entry `tf` cache per query
   (`bm25.rs:62-69`) recovers the speed.

5. **The store stays in the heap.** pg_search discards `.store`
   entirely (§1). vfs's `chunks.content` is the store; the lexical
   index should never carry text, and previews should be served from
   `chunks` by id, as grep's verify pass does.

6. **Over-fetch and retry for liveness.** pg_search's top-k does not
   trust the index for visibility: it fetches `limit × (1 + dead/live)`,
   checks the heap, and re-queries with a doubling chunk (§5). For vfs,
   where an entry can be deleted or re-chunked after the epoch was
   built (`encoded` flips but the epoch rows stay until reclaim), the
   same loop — score client-side, join the top-k candidates to
   `lex_docs`/`entries` for liveness, widen and retry when short — is
   the portable answer to the spec-130 spike's S2 shape without a join
   inside the scoring statement.

7. **Scopes as allow-lists intersected client-side.** pg_search pushes
   only columnar predicates into the query and evaluates everything
   else by heap fetch per candidate (§5). grep's `np.intersect1d`
   against a decoded allow-list is the same design at the client; the
   epoch model can also precompute per-epoch ordinal ranges by
   extension or directory segment (an ordinal → entry map is `lex_docs`)
   and turn a scope into a bitset over ordinals, which is how a fast
   field filter behaves in Tantivy without the fast field.

### Borrow with adaptation

8. **Parallel build as parallel segments, then concatenate rather
   than merge.** pg_search builds ~CPU-count segments in parallel and
   never merges across workers (§4). Because a vfs epoch is rebuilt
   whole, the equivalent is to shard the chunk scan by ordinal range
   across Rust threads, each producing block rows for its range; since
   ordinal ranges are disjoint and ordered, a term's blocks from shard
   k all precede shard k+1's and **no posting merge is needed** — the
   only cost is one partial (vint) block per term per shard, which the
   format already tolerates. `total_num_tokens` and df sum across
   shards exactly as they sum across Tantivy segments. This keeps the
   "two-pass streaming, nothing scales with postings" memory profile
   spec 130's landing note records, per shard.

9. **Block-WAND, client-side, with a shared threshold.** The
   algorithm in §5 needs only: per-term global max, per-block max and
   last-doc, and sequential block decode — all of which the row shape
   in (1)–(2) supplies. Because an epoch is a single doc-id space
   there is one threshold, not one per segment; pg_search's shared
   atomic threshold across parallel workers (§5) is the pattern if the
   client ever scores shards concurrently. For scoped or MaxP queries
   (the spike's S5–S7), the pivot logic is unchanged — the allow-list
   just filters candidates before they are scored.

### What genuinely needs an index AM (and vfs cannot have)

- **Page-granular buffer-manager residency and pins as the
  visibility mechanism** (§1): vfs gets the engine's B-tree page cache
  for free but transfers whole blobs over the wire; there is no
  zero-copy slice and no pin-based grace period — the epoch column
  and `reclaim_epochs` are the substitute, and they already exist.
- **In-engine scoring joined to arbitrary predicates in one plan**
  (ADR 051 pin 1). pg_search does this only for columnar fields and
  otherwise heap-fetches per candidate; a portable blob index scores
  at the client and joins by id afterwards. The spike memo's S3/S4
  results (owned tables win once a predicate is present because the
  planner seeks) are the number to beat with client-side scoring plus
  an id join, and the prototype benchmark should measure exactly that.
- **Incremental writes without a rebuild** — the mutable ctid log,
  `.del` bitsets and layered merging (§4). vfs's fork E4 measured
  incremental maintenance at 97 s per 1 000 entries versus ~4 s for a
  rebuild and chose rebuild; nothing in pg_search's design changes that
  arithmetic for the relational tables, and with blobs the incremental
  path would require rewriting blocks, i.e. a merge. The rebuild
  model stays; what pg_search shows is how much machinery (vacuum
  handshakes, merge locks, background workers) the incremental road
  costs.
- **WAL-integrated durability of the blocks** is automatic in both
  designs — pg_search via generic WAL on ordinary pages (§1), vfs via
  the engine's own logging of row inserts — so this is not a gap.

### Two things not to borrow

- **N over `max_doc`** (deleted docs counted until merge, §3) is an
  artifact of segment immutability; a whole rebuild computes exact N.
- **`source_code`'s parts-only emission** (§7): spec 130's whole-plus-
  parts emission is the better fit for identifier search and should
  stay; the tokenizer is orthogonal to the storage change.

---

**Sources**: `~/Git/Repos/paradedb` @ 7496549 (refreshed 2026-08-26,
default branch `main`, **AGPL-3.0** — studied for design input only,
nothing copied, per CLAUDE.md's rule as amended 2026-08-26: copyleft
clones are fine to study, the no-copy rule is what protects us; note
that `tokenizers/src/code.rs:19-25` itself carries a Quickwit AGPL
notice) — <https://github.com/paradedb/paradedb>;
`~/Git/Repos/tantivy` @ cce9950 (refreshed 2026-08-26, default branch
`main`, **MIT**, crate 0.27.0) — <https://github.com/quickwit-oss/tantivy>;
pg_search's actual engine is the fork `github.com/paradedb/tantivy` at
rev `c3caae3f` (`paradedb/Cargo.toml:69-72`), not cloned. BMW paper:
Ding & Suel, "Faster Top-k Document Retrieval Using Block-Max Indexes"
(SIGIR 2011), cited by `block_wand_union.rs:145-147`.
