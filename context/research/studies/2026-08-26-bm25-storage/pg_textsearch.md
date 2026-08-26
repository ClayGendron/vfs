# Study: pg_textsearch — a block-postings BM25 index inside Postgres, read for vfs's lexical-index storage

- **Study for**: the BM25 storage follow-up to spec 130
  (`../../../specs/archive/130-lexical-index-and-tokenizer/spec.md`,
  landing note: 3.7 KB per chunk, ~40 B per posting, ~1 B rows at 10 M
  chunks) and the SQL Server spike
  (`../../2026-08-26-bm25-vs-mssql-fulltext.md`: 403 s build, 125 MB
  tables vs 7.1 s / 23.5 MB native). The question is which parts of a
  Postgres index-AM design survive translation to portable SQL rows
  (SQLite, Postgres, MySQL/MariaDB, SQL Server, Oracle through
  SQLAlchemy Core; no extensions, no custom access methods).
- **Date**: 2026-08-26
- **Source** (read-only, cited by `path:line`; nothing copied):
  `~/Git/Repos/pg_textsearch` @ `648b25c` (`main`, committed 2026-08-25,
  refreshed 2026-08-26; shallow clone, one commit), PostgreSQL License
  (`LICENSE`). Upstream: <https://github.com/timescale/pg_textsearch>,
  TigerData/Timescale, v1.5.0-dev. Docs read: `README.md`,
  `docs/memtable_v2.md`, `docs/memtable_cache.md`, `CLAUDE.md`,
  `benchmarks/**`.
- **Method**: source reading and grepping only; no execution. Where a
  number is not in the repo (BMW skip rates, MRR) the memo says so.

---

## 1. On-disk unit and layout

**Unit.** One Postgres index relation of 8 KB blocks; every structure is
laid out inside those blocks and mutated through the buffer manager.

**Metapage** (block 0, `constants.h:73`; struct `metapage.h:30-111`):
magic/version, the text-search config OID, `total_docs` and `total_len`
(u64, corpus totals over *persisted segments only* — the invariant
`total_docs = Σ segment.num_docs` is documented at `metapage.h:35-63`),
`k1`/`b`, `level_heads[8]` and `level_counts[8]` for the LSM levels
(`TP_MAX_LEVELS 8`, `constants.h:76`), the memtable chain head/tail
block numbers, and `pending_free_head` for the deferred-free tombstone
chain. Every mutation is a `GenericXLog` record.

**Memtable pages** (the L0 write buffer, on disk since 1.3.0): a singly
linked chain of pages, each `PageHeader` + a 24-byte
`TpMemtablePageHeader` (`page.h:75-89`: magic, version, flags, n_records,
free_offset, next_block, dead_fxid) followed by packed records
`{ctid 6 B, flags 2 B, doc_length 4 B, vector_len 4 B, bm25vector
bytes}` (`page.h:98-107`); records larger than a page span
continuation pages via a FRAGMENT flag (`page.h:197-252`,
`docs/memtable_v2.md` §"Multi-page (FRAGMENT) records"). There is **no
per-term structure in the memtable**: a query walks every record and
builds the few posting lists it needs (`memtable_v2.md` §"Read path";
scoring is exhaustive over it, `bmw.c:404-464`). That is why the chain
is capped at 64 pages (~512 KB) before an auto-spill
(`constants.h:110`) and why `docs/memtable_cache.md` exists.

**Segment** (immutable): a logical byte stream of `data_size` bytes
paged over `SEGMENT_DATA_PER_PAGE = BLCKSZ − SizeOfPageHeaderData` =
8168 bytes per block (`pagemapper.h:27`), with a chain of *page-index*
pages mapping logical page → physical block (`format.h:31-39`;
`segment.c` `tp_segment_open_ex` loads the map, `tp_segment_read`
translates offsets). Section order, from `segment.c:959-960` and the
writer at `segment.c:965-1310`:

| section | contents | bytes |
|---|---|---|
| header `TpSegmentHeader` (`format.h:105-141`) | magic, version 5, num_pages, data_size, level, next_segment, nine section offsets, num_terms, num_docs, total_tokens, alive_count, page_index | ~136 |
| dictionary `TpDictionary` (`format.h:151-156`) | u32 count + sorted array of u32 string-pool offsets | 4 + 4·T |
| string pool `TpStringEntry` (`format.h:169-174`) | `[len u32][text][dict_entry_offset u32]` per term (8 B overhead/term, flagged as a TODO at `format.h:161-167`) | Σ len + 8·T |
| dict entries `TpDictEntry` (`format.h:200-205`) | `skip_index_offset u64, block_count u32, doc_freq u32` | 16·T |
| posting blocks | ≤128 postings each, compressed (§2) | see §2 |
| skip index `TpSkipEntry` (`format.h:236-245`, packed) | `last_doc_id u32, doc_count u8, block_max_tf u16, block_max_norm u8, posting_offset u64, flags u8, reserved[3]` | 20 per block |
| fieldnorm table | one SmallFloat byte per doc (§6) | 1·D |
| ctid map | `BlockNumber` array (4·D) then `OffsetNumber` array (2·D) — segment-local doc id → heap CTID (`docmap.h:7-16`) | 6·D |
| alive bitset | 1 bit per doc, all set at write (`alive_bitset.h:1-10`, `segment.c:1300-1310`) | D/8 |

Term lookup is a binary search over the sorted string offsets with
`strcmp` against the pool (`segment/scan.c:100-152`), i.e. O(log T)
page reads per term per segment. Doc ids are **segment-local u32,
assigned in CTID order** (`docmap.h:14-16`), and a term's postings are
sorted by doc id before blocking (`segment.c:1184`, with the comment
explaining the concurrent-insert bug that forced the sort).

**Block size and contents.** `TP_BLOCK_SIZE 128` documents per block
("matches Tantivy", `format.h:210`). A posting is
`TpBlockPosting {doc_id u32, frequency u16, fieldnorm u8, reserved u8}`
(`format.h:268-274`) — the fieldnorm is duplicated **inline in every
posting** so scoring never does a per-posting buffer lookup
(`format.h:262-266`: "each buffer manager access adds ~300-500ns").

## 2. Posting compression

`compression.h:21-25` and `:62-66`; encoder `compression.c:199-259`,
decoder `:272-343`:

```
[2 B header: doc_id_bits (1..32), freq_bits (1..16)]
[ceil(n · doc_id_bits / 8) B : bitpacked doc-id deltas]
[ceil(n · freq_bits / 8) B   : bitpacked term frequencies]
[n B                         : raw fieldnorm bytes]
```

- **Delta scheme**: first delta is the absolute doc id (the decoder is
  called with `first_doc_id = 0`, `segment/scan.c` load_block), later
  deltas are gaps. One bit width per block for ids and one for tfs,
  chosen as `ceil(log2(max+1))` (`compression.c:29-41`). No
  frame-of-reference base, no patching: `TP_BLOCK_FLAG_FOR/PFOR` are
  reserved "Phase 3" flags (`format.h:252-255`) and only
  `TP_BLOCK_FLAG_DELTA` is ever written (`segment.c:1225-1229`).
- **tf** is stored as the packed frequency (u16 in memory; `int32`
  frequencies are cast to `uint16` without a clamp at
  `build_context.c:191` and `segment.c:1149`).
- Worst case 898 B per block (`compression.h:32`); a dense-ish block of
  128 postings with 10-bit gaps and 3-bit tfs is 2 + 160 + 48 + 128 =
  338 B, i.e. **~2.6 B per posting plus 20/128 B of skip entry**.
  Roughly 1 B of every posting is the inline fieldnorm.
- Decode is branchless direct-indexed 8-byte loads with SSE2/NEON
  mask+store (`compression.c:78-188`); blocks are read into a reusable
  898-byte buffer (`segment/scan.c` load_block; `bmw.c:1050-1051`).
- Compression is a GUC (`pg_textsearch.compress_segments`, README
  "Segment compression"); uncompressed blocks are 8 B/posting and can be
  read zero-copy from the buffer page when 4-byte aligned
  (`segment/scan.c` load_block, uncompressed branch).

## 3. Corpus statistics

- **N and avg_dl** are computed at query time: `metap.total_docs +
  chain_source.total_docs`, same for `total_len`, then `avg_doc_len =
  total_len / total_docs` (`bm25.c:155-184`; the chain source sums its
  records at open, `chain_source.c:660-680`). The metapage totals are
  bumped at spill (`log.c:770-771`), set by the build
  (`build.c` tp_build final metapage write; `build_parallel.c:826-829`),
  and shrunk by merge and VACUUM only when a segment's `num_docs`
  changes or a segment leaves the chain (`merge.c:1758-1810`,
  `vacuum.c:256-300`). **Bitset-dead docs stay in N and total_len** until
  a merge rewrites them (`metapage.h:44-48`).
- **df** lives per segment in `TpDictEntry.doc_freq` and is the count of
  postings the term had at write time (`build_context.c:239`:
  `doc_freq = expull.num_entries`). Global df = memtable df (per-term
  accumulator, `chain_source.c:414-429`) + Σ over every segment on every
  level (`bm25.c:46-71`; the batch form opens each segment once for all
  query terms, `bm25.c:82-111`). This is additive because a CTID lives
  in exactly one place: the memtable, or one segment (merge de-duplicates
  through the docmap; parallel workers scan disjoint block ranges,
  `build_parallel.c:591-609`).
- **Deletes**: flipping an alive bit does not touch `doc_freq`
  (`vacuum.c:816-853`), so df over-counts until the next merge, when the
  new segment's `doc_freq` is recomputed from surviving postings. That
  staleness is accepted, and N over-counts in the same direction, so idf
  drifts slowly rather than wildly.
- **idf** is never stored: `ln(1 + (N − df + 0.5)/(df + 0.5))`
  (`bm25.c:28-35`) — the same Lucene form spec 130 adopted. The
  standalone `<@>` operator caches (term → df, idf) per statement because
  opening every segment per row was "catastrophic" (`types/query.c`
  ~1003).
- Partitioned tables keep partition-local N/avg_dl/df, so cross-partition
  scores are not comparable (README "Partitioned Tables").

## 4. Build path

**Serial `CREATE INDEX`** (`build.c:1263` `tp_build`; per-tuple callback
`build.c:1180-1260`): `table_index_build_scan` feeds each tuple to
`tp_tokenize_text`, the terms go into a `TpBuildContext` — a bump-arena
of 1 MB pages addressed by 32-bit `ArenaAddr` (12-bit page, 20-bit
offset; 4 GB cap, `arena.h:14-34`) plus an `HTAB` term → `TpExpull`, an
"exponential unrolled linked list" of packed 7-byte entries `{doc_id
u32, tf u16, norm u8}` in blocks that double from 32 B to 32 KB
(`expull.h:24-69`, "Inspired by Tantivy's ExpUnrolledLinkedList"), and
flat per-doc fieldnorm/CTID arrays (`build_context.h:49-68`). Doc ids are
assigned sequentially and the fieldnorm encoded at add time
(`build_context.c:120-190`). When arena bytes reach the budget —
`maintenance_work_mem`, clamped to ¾ of the 4 GB arena
(`build.c:1484-1490`, `arena.h:96-104`, `build_context.h:99-105`) — the
context is written as an L0 segment straight from the EXPULL lists
(`tp_write_segment_from_build_ctx`, `build_context.c:260`), linked as the
L0 head (`build.c:320`), and `tp_maybe_compact_level(0)` runs
(`build.c:1245`), so tiered compaction happens *during* the build.

**Parallel build** (`build_parallel.c`, "leader-only merge"): taken when
the planner granted workers, `reltuples ≥ 100 000`, and not
CONCURRENTLY (`build.c:1344-1365`); the README states the planner needs
`maintenance_work_mem ≥ 64 MB` to grant any. The leader splits the heap
into contiguous, disjoint block ranges (`build_parallel.c:591-609`), so
worker outputs have disjoint CTIDs. Each worker gets
`maintenance_work_mem / nworkers`, minimum 64 MB, arena-clamped
(`:261-274`), builds the same `TpBuildContext`, and on every budget
flush writes a *flat* segment (same format, no page index; header and
dict entries patched by seek-back) into its own `BufFile` in a
`SharedFileSet` (`tp_write_segment_to_buffile`, `build_context.c:741`).
A worker may produce at most 64 segments or the build ERRORs with a hint
to raise `maintenance_work_mem` (`build_parallel.c:425-440`). The leader
then opens every worker segment through `tp_segment_open_from_buffile`,
does one N-way dictionary merge by linear minimum scan
(`build_parallel.c:734-786`, `merge_find_min_source`), streams the
posting lists block by block into **one** L0 segment on real pages
(`:796-804`, `write_merged_segment_to_sink` with `disjoint_sources=true`
so the docmap merge is a concatenation, `merge.c:755-775`), and writes
`total_docs/total_len` to the metapage (`:826-829`). The merge is
single-threaded; their own 138 M-doc note says it "dominates at this
scale" (`benchmarks/gh-pages/comparison.html:533-537`). Merge memory:
an `old_to_new` u32 array per source doc (~2.5 GB for 138 M docs across
24 segments, `merge.c:655-657`).

**Incremental insert** (`build.c:1694` `tp_insert`): tokenize to a
`bm25vector` outside any lock; under the per-index LWLock SHARED append
one record to the chain tail page (tail buffer EXCL + one `GenericXLog`
record; `memtable_v2.md` §"Write path"). Auto-spill fires when the chain
passes `memtable_pages_threshold` (64 pages, `constants.h:110`;
`tp_auto_spill_if_needed`) or at commit when a transaction added
`bulk_load_threshold` = 100 000 terms (`constants.h:88`,
`log.c:980-992`). Spill (`build.c:136-250`, `tp_do_spill`): extract sorted
`TermInfo[]` + docmap from the chain, `tp_write_segment`, then
`tp_spill_finalize` (`log.c:704-775`: one `GenericXLog` over metapage +
new header — L0 head, `total_docs += delta`, chain pointers cleared),
stamp the old chain pages DEAD for a later FSM reclaim, then
`tp_maybe_compact_level(0)`. VACUUM also spills (`vacuum.c:1140-1150`).

**Compaction** is tiered and synchronous in the inserting backend
(README "No Background Compaction"): when `level_counts[L] ≥
segments_per_level` (default 8, GUC 2–64) merge 8 segments into one at
L+1, repeat while the level is still full, then recurse to L+1
(`merge.c:1926-1975`). `tp_merge_level_segments` (`:1439`) opens the
sources, N-way merges dictionaries, streams posting blocks
(`TpPostingMergeSource`, `merge_internal.h:71-85`), rebuilds the docmap
in CTID order dropping bitset-dead docs (`merge.c:661-895`), writes the
new segment, and in one metapage record swaps the level chains, applies
`total_docs/total_len` shrinkage, and parks the displaced pages in a
tombstone chain (`:1758-1890`). `bm25_force_merge` merges every level in
one batch and truncates the relation (`merge.c:1981-2002`,
`build.c` `tp_force_merge`).

## 5. Top-k: Block-Max WAND

**Per-block metadata** (written at `segment.c:1200-1216`,
`build_context.c:455-467`): `last_doc_id`, `doc_count`, `block_max_tf`
(u16) and `block_max_norm` — despite the name the **minimum** fieldnorm
byte in the block, i.e. the shortest document (`format.h:240-241`). The
block upper bound is plain BM25 evaluated at `(tf = max_tf, dl =
decode(min_norm))` (`bmw.c:365-377`) — valid because the term score is
monotone increasing in tf and decreasing in dl.

**What it costs**: 20 B per 128 postings (0.16 B/posting) on disk; per
query, per term, per segment, every skip entry is read up front and
turned into `block_max_scores[]` and `block_last_doc_ids[]`
(`bmw.c:1017-1052`), so a common term with 2 M postings costs ~15 600
skip entries (~312 KB) of reads before any block is touched, and a
`max_score` per term = max over blocks × query term frequency
(`:1042-1046`).

**Threshold**: a min-heap of capacity k (`bmw.h:32-73`); threshold =
root once full, else 0 (`bmw.h:58-62`). k is the pushed-down LIMIT,
accepted only when the scan has one ORDER BY and no index quals
(`limit.c:117-143`, `cost.c:109-131`); a Filter above the scan seeds k to
`ceil(3 · LIMIT / selectivity)` (`cost.c:47-79`). Without a LIMIT k =
`default_limit` 1000 (`constants.h:85`). If the executor drains the batch
the scan doubles k and re-runs the whole query, up to 100 000
(`access/scan.c:499-513`). The memtable is scored exhaustively **first**
(`bmw.c:603-605`, `:1666-1668`), which primes the threshold before any
segment block is considered.

**Single term** (`bmw.c:469-571`): precompute every block bound, then
skip any block with `block_max < threshold`, decode the rest.

**Multi-term** (`bmw.c:1476-1617`), per segment: terms sorted by current
doc id; **pivot** = shortest prefix whose Σ `max_score` exceeds the
threshold (`find_wand_pivot`, `:1164-1202`); pre-pivot terms seek to the
pivot doc by binary search over the cached `block_last_doc_ids` and load
only the target block (`seek_term_to_doc`, `:853-983`); **block-max
refinement**: skip only if Σ(pivot terms' *current block* bound) +
Σ(non-pivot terms' *global* max) ≤ threshold (`:1525-1571`, the comment
records issue #365 where using the block bound alone lost top-k
candidates); on a skip, advance the pivot term whose block ends soonest
to `min_block_end + 1` (`block_max_skip_advance`, `:1251-1344`, issue
#355: picking the highest-max term could fail to make progress). Aligned
pivots are scored by summing per-term contributions (`:1429-1462`),
dead docs are filtered by the alive bitset (`:1580-1586`), and CTIDs are
resolved lazily per segment at extraction (`:260-295`).

**What it gains — their numbers.** The repo has no published skip-rate
or "BMW vs exhaustive" figure: `pg_textsearch.log_bmw_stats` prints
blocks scanned/skipped and seeks (`bm25.c:236-254`) but the regression
tests deliberately filter that line out
(`test/expected/bmw_skip_advance.out:69-73`). What is published is
end-to-end latency: on MS MARCO v1 (8.8 M passages, one force-merged
segment) p50 0.70 ms for 1-token queries, 1.53 / 3.00 / 4.52 ms for
2/3/4 tokens (`benchmarks/gh-pages/comparison.html:226-260`); on
MS MARCO v2 (138 M passages) p50 5.1 ms (1 token), 9.1, 20.0, 41.9,
67.8, 102.8, 159.4, 178.0 ms for 2…8+ tokens
(`benchmarks/datasets/msmarco-v2/results/20260304_tapir_latest/summary.md:22-36`).
Latency grows roughly linearly with term count, which is the WAND
signature (per-term skip arrays and pivot work), not the exhaustive one.

## 6. Document length: SmallFloat quantization

`fieldnorm.h:6-17` and the 256-entry decode table `fieldnorm.c:17-303`
(Lucene `SmallFloat.byte4ToInt`): lengths 0–39 exact; then eight
buckets per doubling (step 2 from 40, step 4 from 56, step 8 from 88, …,
step 2^27 at the top, reaching 2.01 × 10^9). `encode_fieldnorm` is a
binary search for the largest table value ≤ length (`fieldnorm.c:311-326`),
i.e. **floor** to the bucket. Reading the table: the worst relative
error sits in the first bucket of each octave and converges to ~11 %
(e.g. 1175 → 1048 is 10.8 %; 95 → 88 is 7.4 %), the last bucket of each
octave is ~5–6 %, and the mean over a bucket is about half the maximum —
so the header's "~6 % relative error max" is the typical figure, not the
bound.

Why they accept it (`fieldnorm.h:8-17`, `format.h:262-266`): BM25 sees
`dl / avg_dl` under `b = 0.75`, so a ~10 % length error moves the
length-normalization factor by ~7 % and the score by less; in exchange a
document's length is 1 byte and can be carried **inline in every
posting**, so scoring a block needs no per-posting lookup (the "300–500
ns per buffer access" argument). Consistency is enforced: the standalone
operator quantizes the document length through the same encode/decode
so operator and index scores agree (`types/query.c:949-957`). `avg_dl`
itself stays exact (metapage `total_len` is the raw sum), except that a
merge subtracts *decoded* fieldnorms for dead docs (`merge.c:846-873`).
The fieldnorm is stored twice: the per-doc table and the inline byte.

## 7. Tokenizer boundary

- Documents are tokenized by calling Postgres's `to_tsvector_byid` with
  the index's `text_config` OID (`build.c:815-850`, `:995-1003`); tf is
  the number of positions the tsvector recorded for the lexeme, or 1
  when there are none (`build.c:776-779`). Stemming, stop words,
  case-folding, and word splitting are therefore entirely the text
  search configuration's (`english` stems and drops stop words,
  `simple` does neither — README "Indexing").
- Documents over 256 KB are split at the last ASCII whitespace inside
  each window because a tsvector caps its lexeme pool at 1 MB
  (`build.c:812`, `tp_find_chunk_boundary` `:868-905`, chunk loop
  `:975-1050`); per-chunk (term, freq) pairs are sorted and collapsed.
- Queries are tokenized with the same configuration (`types/query.c`
  ~943-950); the query term's own frequency multiplies its contribution
  (`bmw.c:657`, `:760-761`, `:1046`).
- **Identifiers and code**: there is no code-aware handling at all — no
  camelCase/snake_case splitting, no identifier whole-plus-parts
  emission (grep for `camel`, `snake`, `identifier` in `src/` finds
  nothing). What happens to `pthread_create` is whatever the chosen
  parser does. The README's CJK section makes the same point from the
  other side: the default parser does not split CJK, so a zhparser
  configuration is needed. Two limits are inherited from Postgres and
  visible only as README prose, not code: the 2047-character lexeme
  limit (`MAXSTRLEN`) and the tsvector position cap that bounds tf (the
  repo never mentions the latter; `uint16` truncation at
  `build_context.c:191` is the only in-repo cap).

## 8. Deletes, updates, and visibility

- The index stores heap CTIDs and has **no visibility of its own**: an
  index scan returns CTIDs and the executor's heap fetch applies MVCC.
  A deleted-but-unvacuumed row is still scored, still counted in N and
  df, and is dropped only after ranking — which is why a LIMIT k scan
  can come up short and re-executes with 2k (`access/scan.c:499-513`),
  and why the README warns about post-filtering.
- UPDATE is an insert of the new CTID into the memtable; the old CTID
  becomes dead in the heap.
- VACUUM `ambulkdelete` (`vacuum.c:871-1110`): spill the memtable first
  so everything is in segments; walk every segment's CTID map calling
  the dead-tuple callback; for V5 segments flip bits in the alive bitset
  under `GenericXLog` (`tp_vacuum_mark_dead`, `:816-853`,
  `alive_bitset.c:135`); a segment whose bitset empties is unlinked and
  its pages parked; pre-V5 segments are rebuilt. `total_docs/total_len`
  shrink only for dropped/rebuilt segments (`:989-1080`); `reltuples`
  reports Σ `alive_count` (`:226-252`). Scoring skips dead docs by
  reading one bitset byte per posting, but only when the segment has any
  dead docs (`alive_bitset.h:47-60`). Dead docs are physically purged at
  the next merge (`merge.c:766-800`).
- Displaced pages are never freed immediately: a merge parks them in a
  WAL-logged tombstone chain stamped with a `FullTransactionId`, and they
  return to the FSM only when that horizon is older than
  `GetOldestNonRemovableTransactionId` — so hot standbys need
  `hot_standby_feedback = on` (`tombstone.h:5-14`, `CLAUDE.md` "Standby-safe
  segment reclaim").
- **Versus vfs's epoch rebuild**: pg_textsearch amortizes deletes with a
  bitset and repairs df/N at merge; vfs never mutates an epoch, hides
  stale entries through `encoded`/liveness joins at query time (exact,
  no over-counting once the reindex has run), and drops the whole old
  epoch. pg_textsearch's staleness window is "until merge"; vfs's is
  "until reindex", and vfs's statistics are exact at every epoch
  because they are rebuilt from scratch.

## 9. Sizes, build numbers, and the benchmark setup

From `benchmarks/gh-pages/comparison.html` (MS MARCO v1, 8 841 823
passages, `:181-224`): index **1 215 MB** (ParadeDB 1 503 MB), build
**233.5 s** (ParadeDB 140.1 s; "down from 270 s" after the arena
allocator and leader-only merge, PRs #231/#244). Note the size caveat
they state themselves: no positions are stored, so no phrase queries
(`:210-214`).

From `benchmarks/datasets/msmarco-v2/results/20260304_tapir_latest/summary.md`
(MS MARCO v2, 138 364 158 passages, 2026-03-10, commit fb3b3b1,
c6i.4xlarge 8C/16T 123 GB NVMe, Postgres 17.7, `shared_buffers = 31 GB`):
build **17 min 37 s** with 15 of 15 workers (ParadeDB 8:55 with 14),
index **17 GB** (18 153 144 320 B; ParadeDB 23 GB), **17 373 764 unique
terms**, avg doc length **29.34 lexemes**, one L0 segment of 2 214 872
pages; single-client 62.9 ms/query over 691 queries; 16-client pgbench
91.4 TPS. Dividing: 131 B per document; postings ≤ 138.36 M × 29.34 ≈
4.06 G, so the whole index (dictionary, skip index, fieldnorms, CTID
map, page headers included) is **≥ 4.5 B per posting** — against vfs's
measured ~40 B per `lex_terms` row (`spec.md` landing note; 99 MB /
3.09 M rows = 32 B in `lex_terms` alone, 3.7 KB per chunk all in).

Setup (`benchmarks/README.md`; `datasets/msmarco-v2/queries.sql:1-80`):
queries pre-sampled by token count into 8 buckets, 100 per bucket (53
and 38 for the top two), 50-query warm-up, each timed as
`SELECT COUNT(*) FROM (SELECT passage_id … ORDER BY passage_text <@>
to_bm25query($1, idx) LIMIT 10)`, p50/p95/p99 per bucket and a
token-weighted p50. Loads run `bm25_force_merge` right after
`CREATE INDEX` so the query numbers are over **one segment**
(`datasets/msmarco/load.sql:96-100`); `run_full_benchmark.sh:138-139`
sets `maintenance_work_mem` and `max_parallel_maintenance_workers`
explicitly; `run_parallel_scaling.sh` builds with 0/1/2/4 workers.
Ground-truth files exist for correctness validation, but no MRR@10
results are stored in the repo (the README lists it as a metric; the
`results/` directory is gitignored).

Memtable microbenchmark (`docs/memtable_v2.md:489-501`, PG 18 default
GUCs): 50 k bulk INSERT ~2.20 s (~44 µs/doc), 10 k post-spill INSERTs
~204 ms, and a query against a 10 k-doc memtable ~15 ms vs ~1.5 ms — the
linear memtable read that motivated the 64-page spill cap and the
in-memory cache design.

## 10. What a portable-SQL reimplementation can borrow

vfs already runs the gram index in the shape pg_textsearch uses for
segments: one row per `(epoch, gram_key)` holding a delta+varint blob
(`src/vfs/models/rows.py:504-521`, `models/postings.py:1-70`), built by
`crates/vfs-core` with a byte-identical Python fallback, fetched by
`IN`-list and intersected client-side (`grep.py`). The lexical index
does not (`rows.py:545-585`: one row per (term, chunk)). The following
maps cleanly.

**Borrow structurally**

1. **Block-per-row postings** — `lex_blocks(epoch, term_id, block_no) →
   blob` of ≤128 postings in pg_textsearch's exact block format (2-byte
   widths header, bitpacked deltas, bitpacked tfs, then per-posting
   norm or weight bytes), with the **skip entry as columns** on the same
   row: `last_doc_no, doc_count, max_tf, min_norm`. The gram codec's
   count-prefixed varint blob is the simpler cousin; bitpacking at a
   per-block width is what buys the extra ~2× on dense runs and is a
   few dozen lines in Rust with a pure-Python mirror. Row count falls
   from Σ df to Σ ceil(df/128): on the 4 000-file sample (487 k terms,
   3.09 M postings) ≈ 487 k + 24 k ≈ **0.5 M rows instead of 3.09 M**,
   and at 10 M chunks / ~1 G postings on the order of 10^7 rows instead
   of 10^9. Bytes: ~3 B per posting in-blob, so the 99 MB `lex_terms`
   becomes roughly 10–15 MB plus the dictionary. Bind budgets stop
   mattering (MSSQL's 3 700 statements become tens), reclaim deletes
   10^7 rows, not 10^9, and MySQL's `LONGBLOB` variant already exists.
2. **Dense per-epoch doc numbers** — pg_textsearch's docmap. vfs chunk
   ids are sparse BIGINTs allocated across epochs, so raw gaps can need
   many bits; assign a dense `doc_no` per epoch in `lex_docs` (it already
   has one row per chunk) and encode blocks over `doc_no`. Resolution to
   `chunk_id`/`entry_id` is the `lex_docs` join vfs performs anyway —
   the SQL analogue of the lazy CTID map.
3. **Per-block max for skipping, done better than pg_textsearch can** —
   because an epoch's `avg_dl`, `N`, and `df` are fixed at build, vfs can
   precompute the exact per-block upper bound `block_max_weight = max_j
   idf · tfc(tf_j, dl_j)` (no `min_norm`/`max_tf` decoupling, hence a
   tighter bound) and store it as a column, plus a per-term `max_weight`
   on `lex_df` for WAND pivoting. Then a query is: one `lex_df` probe for
   (idf, df, max_weight), a first fetch of block rows ordered by
   `block_max_weight DESC` for the rare terms to establish a threshold,
   and for the common terms only blocks with `block_max_weight ≥
   threshold` — the `df`-ceiling problem from the MSSQL spike (`struct`,
   `return`: 3–6 k rows summed in full) becomes "fetch the top few blocks
   of a 15 k-block term". This is portable `WHERE term_id = ? AND
   block_max_weight >= ?` on an indexed column; pg_textsearch has to
   recompute bounds per query because its `avg_dl` moves.
4. **Quantized lengths inline, or quantized weights** — pg_textsearch's
   1-byte SmallFloat norm per posting removes the per-posting length
   lookup. vfs has two better options because `avg_dl` is epoch-fixed:
   (a) keep `tf` bitpacked and one SmallFloat norm byte per posting
   (~11 % worst-case dl error, self-contained blocks, no join during
   scoring), or (b) store the exact `weight` spec 130 already computes,
   quantized to one or two bytes on a log scale (a 1-byte log-quantized
   weight is ~1 % relative error, far tighter than (a) and still no
   join). Either way `lex_docs.dl` stays exact for stats and for the
   fidelity referee.
5. **Stats rows** — `lex_df(df, idf)` and `lex_stats(n_docs, avg_dl)`
   are exactly pg_textsearch's dictionary `doc_freq` and metapage
   totals; keeping idf materialized is a vfs advantage pg_textsearch
   gives up for incremental correctness. Add `block_count` and
   `max_weight` to `lex_df` and the WAND pivot needs no block reads.
6. **Term ids in the block key** — pg_textsearch's per-segment string
   dictionary with binary search is the AM-side equivalent of vfs fork
   E2; an integer `term_id` on `lex_df` and `lex_blocks` shrinks keys and
   binds and is the natural join column.
7. **The build shape** — arena + per-term append lists flushed at a byte
   budget, then an N-way merge of sorted runs into one segment, is a
   good template for the Rust engine: tokenize a batch, accumulate
   (term → postings) in memory to a declared budget, spill sorted runs
   to a temp file, merge runs into block rows. vfs's epoch rebuild is
   pg_textsearch's "parallel build + `bm25_force_merge`" run every time,
   so vfs always has **one segment, no levels, no compaction, no vacuum
   rewrite** — the simplest case of their design.

**Genuinely requires an index AM (do not try to port)**

- Page-level buffer locking and `GenericXLog` page deltas: replaced by
  transactional row inserts under bind budgets — the cost vfs measured
  (403 s on MSSQL) is a row-count problem, which item 1 removes.
- The memtable/LSM incremental path (chain pages, spill, tiered merge,
  tombstones, standby horizons): this is the whole apparatus for
  mutating an index in place under concurrency, and their own numbers
  show its read side is linear and had to be capped. vfs's epoch
  rebuild sidesteps all of it. If incremental freshness is ever wanted,
  the SQL analogue is a small row-per-posting delta table (spec 130's
  current shape) consulted alongside the block table and folded in at
  the next reindex — a two-tier design in SQL, and spec 130's landing
  note already measured why it should stay small.
- Alive bitsets and lazy df repair: vfs's liveness join is exact and
  free.
- Zero-copy page access, SIMD decode, and reusable buffers: vfs decodes
  fetched blobs in Rust client-side; the same optimizations apply there.

**Trade-offs for vfs's epoch-rebuild model, concretely**

- Rows per epoch ≈ (distinct terms) + Σ ceil(df/128); rare terms
  dominate the count (one row each), so vocabulary size, not posting
  count, sets the row floor — term ids and a 64-byte term cap (spec 130)
  keep the dictionary small. Reclaim drops one epoch's ~10^7 rows.
- Query cost per term = 1 dictionary probe + ceil(df/128) block rows,
  or with item 3 only the competitive blocks; multi-term intersection
  and WAND run client-side over decoded blocks, as grep already does
  over gram blobs. `IN` lists are over query terms only.
- Scoring fidelity: with exact stored weights (item 4b) the fidelity
  referee (top-10 identity, τ = 1.0) holds as today; with SmallFloat
  norms (4a) it would need a tolerance — prefer 4b.
- Build memory: one term → postings map per batch to a declared budget,
  spilled runs merged; nothing scales with the corpus in memory, which
  is the same profile spec 130 required.
- Statement shapes stay bounded: block blobs are ≤ ~1 KB, one row per
  block, batch inserts under `insertmanyvalues`.

## Sources

- `~/Git/Repos/pg_textsearch` @ `648b25c57f91635341fac01676c015405665d2bb`
  (`main`, 2026-08-25; refreshed and read 2026-08-26), PostgreSQL
  License — <https://github.com/timescale/pg_textsearch>. Files cited:
  `src/constants.h`, `src/segment/{format.h,compression.h,compression.c,
  fieldnorm.h,fieldnorm.c,segment.c,scan.c,merge.c,merge_internal.h,
  docmap.h,alive_bitset.h,alive_bitset.c,tombstone.h,pagemapper.h,io.h}`,
  `src/scoring/{bm25.c,bm25.h,bmw.c,bmw.h}`, `src/index/{metapage.h,limit.c}`,
  `src/planner/cost.c`, `src/access/{build.c,build_parallel.c,
  build_context.c,build_context.h,vacuum.c,scan.c}`,
  `src/memtable/{page.h,log.c,chain_source.c,arena.h,expull.h}`,
  `src/types/query.c`, `docs/memtable_v2.md`, `docs/memtable_cache.md`,
  `README.md`, `CLAUDE.md`, `benchmarks/README.md`,
  `benchmarks/gh-pages/comparison.html`,
  `benchmarks/datasets/msmarco-v2/results/20260304_tapir_latest/summary.md`,
  `benchmarks/datasets/msmarco-v2/queries.sql`,
  `benchmarks/datasets/msmarco/load.sql`, `test/expected/bmw_skip_advance.out`.
- In-tree: `context/specs/archive/130-lexical-index-and-tokenizer/spec.md`,
  `context/research/2026-08-26-bm25-vs-mssql-fulltext.md`,
  `src/vfs/models/rows.py`, `src/vfs/models/postings.py`,
  `src/vfs/storage/backends/database/indexing.py`.
