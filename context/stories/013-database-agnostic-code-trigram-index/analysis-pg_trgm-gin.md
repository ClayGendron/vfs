# Analysis — pg_trgm / GIN source vs. VFS code-trigram index design

> Date: 2026-05-25
> Scope: validate VFS story 013's staging/flush/compression design and its
> "no `pg_trgm` as the index" decision against the PostgreSQL `pg_trgm` extension
> and the GIN access method source.
> Source tree studied: `/Users/claygendron/Git/Repos/postgres`
> (`contrib/pg_trgm/`, `src/backend/access/gin/`).

---

## Findings

### 1. GIN `fastupdate` pending list (the staging->flush analog)

- **What the pending list is.** With `fastupdate=on` GIN buffers new entries in
  unsorted "list pages" scanned linearly at search time and merged into the main
  b-tree later. `README:97-105`: *"if the fast-update feature is enabled, there
  can be 'list pages' holding 'pending' key entries that haven't yet been merged
  into the main btree. The list pages have to be scanned linearly when doing a
  search, so the pending entries should be merged into the main btree before
  there get to be too many of them. The advantage of the pending list is that
  bulk insertion of a few thousand entries can be much faster than retail
  insertion."* Exactly VFS's staging-delta-log -> posting-block model: cheap
  unordered appends now, ordered merge later, read cost grows with pending size.

- **One TID per pending entry; no posting list yet.** `README:201-205`: *"there
  is always exactly one heap itempointer associated with a pending entry... There
  is no posting list."* Mirrors VFS staging holding one
  `(gram_key, entry_id, action)` row per change, before any folding.

- **Flush trigger / threshold.** `ginfast.c:448-471`:
  ```c
  cleanupSize = GinGetPendingListCleanupSize(index);
  if (metadata->nPendingPages * GIN_PAGE_FREESIZE > cleanupSize * (Size) 1024)
      needCleanup = true;
  ...
  if (needCleanup)
      ginInsertCleanup(ginstate, false, true, false, NULL);
  ```
  Size trigger is `gin_pending_list_limit`. **Default = 4096 KB (4 MB), min 64 KB**:
  `guc_parameters.dat:1199-1206` (`boot_val => '4096'`, `min => '64'`,
  `GUC_UNIT_KB`); `postgresql.conf.sample:818` (`#gin_pending_list_limit = 4MB`).
  Cleanup also fires from VACUUM/analyze and `gin_clean_pending_list()`
  (`ginfast.c:780-816`, `README:5-7`). Three flush paths: size threshold on
  insert, vacuum, manual.

- **`work_mem` vs `maintenance_work_mem` -- confirmed and precise.**
  `ginInsertCleanup` picks its budget by who called it (`ginfast.c:807-828`):
  ```c
  if (forceCleanup) {                  // vacuum/analyze/gin_clean_pending_list
      LockPage(... ExclusiveLock);
      workMemory = (AmAutoVacuumWorkerProcess() && autovacuum_work_mem != -1)
                   ? autovacuum_work_mem : maintenance_work_mem;
  } else {                             // piggybacked on a user INSERT
      if (!ConditionalLockPage(... ExclusiveLock)) return;
      workMemory = work_mem;
  }
  ```
  Intent comment `ginfast.c:448-454`: *"In non-vacuum mode, it shouldn't require
  maintenance_work_mem, so fire it while pending list is still small enough to
  fit into gin_pending_list_limit."* Foreground (insert-triggered) cleanup is
  sized for the smaller `work_mem`; the exhaustive cleanup uses
  `maintenance_work_mem`. This is VFS's "small frequent flush vs. periodic large
  compaction" tiering, with an exact precedent.

- **Inline-cleanup-stalls-the-writer is a real, documented failure mode.**
  The non-vacuum cleanup at `ginfast.c:466-471` runs *inside the user insert
  path* once the threshold trips; comment `ginfast.c:449-451`:
  *"ginInsertCleanup could take significant amount of time."* Exactly VFS's
  "synchronous compaction stalls the unlucky write." PG mitigates by taking the
  metapage lock *conditionally* (`ConditionalLockPage`, line 825) and bailing if
  another backend is already cleaning -- so writers never pile up on one cleanup.

### 2. GIN posting storage & compression (the posting-block analog)

- **Inline posting list, then promotion to a "posting tree."** TIDs stored
  inline in the leaf tuple until they no longer fit, then spill to a separate
  b-tree of posting pages (`README:95-105,142-147`). Promotion in
  `gininsert.c:245-284`:
  ```c
  compressedList = ginCompressPostingList(newItems, newNPosting, GinMaxItemSize, &nwritten);
  if (nwritten == newNPosting) { res = GinFormTuple(...); }   // still fits inline
  ...
  if (!res) {  // posting list would be too big, convert to posting tree
      postingRoot = createPostingTree(...);
  }
  ```
  **Promotion threshold = `GinMaxItemSize`** (`ginblock.h:249-253`),
  `MAXALIGN_DOWN((BLCKSZ - pageheader - opaque) / 3)` -- roughly one third of an
  8 KB page (~2.7 KB of *compressed* bytes). Below -> inline; above -> posting
  tree. GIN's analog of "one small block" vs. "promote to multi-block."

- **Posting lists split into bounded segments, not one big list.**
  `README:269-275`: *"lists (also called segments), instead of one big one...
  an update only needs to re-encode the affected segment."* Sizing constants
  (`gindatapage.c:34-35`): **`GinPostingListSegmentMaxSize 384`**,
  **`GinPostingListSegmentTargetSize 256`** (bytes); repack targets 256 / splits
  at 384 (`gindatapage.c:1513,1606-1627`). Exactly VFS's "many immutable bounded
  blocks, re-encode only the affected block" -- GIN bounds by **encoded bytes**
  (256/384 B), VFS by **doc-id count** (1,024/4,096/8,192). Both make one edit
  touch one bounded unit, not the whole posting list.

- **Compression = exactly VFS's `delta -> varint` v1.** `README:280-304`:
  *"item pointers are stored in sorted order... we store the difference from the
  previous item... varbyte encoding."* Code (`ginpostinglist.c`):
  - first item stored **uncompressed** as the segment anchor
    (`ginCompressPostingList:215`: `result->first = ipd[0]`);
  - each subsequent item is `delta = val - prev` (line 224),
    `Assert(val > prev)` (line 226) -- sorted, strictly increasing, deltas only;
  - `encode_varbyte` (lines 114-127): canonical 7-bits/byte, high-bit
    continuation varint;
  - TID packed into one 64-bit int, offset in low 11 bits
    (`MaxHeapTuplesPerPageBits 11`, lines 81,92-105), <= 6 bytes per item
    (`README:295-299`).

  Validates VFS's "sorted int doc IDs -> delta (gap) encode -> varint" v1 as the
  same primitive GIN ships. One difference: GIN does **not** layer zstd/gzip on
  top (its bound is a page); VFS's optional zstd/gzip is an addition GIN neither
  validates nor needs.

### 3. pg_trgm trigram extraction -- VFS's rejection reasons are CORRECT

- **Word-oriented tokenization; punctuation dropped.** `generate_trgm_only`
  (`trgm_op.c:493-589`) loops `find_word` (`trgm_op.c:337-366`), advancing over
  any char where `ISWORDCHR(c,len)` is false. `ISWORDCHR` = `t_isalnum_with_len`
  (`trgm.h:50`). So `foo|bar` -> words `foo` and `bar`; the `|` and trigrams
  crossing it (`o|b`, `|ba`) never enter the index. VFS's examples
  (`foo|bar`, `path/to/file.py`, `async def _grep_impl(`) are precisely what
  pg_trgm cannot represent. VFS correct.

- **Word padding `LPADDING=2`, `RPADDING=1`.** `trgm.h:16-17`; applied in
  `generate_trgm_only` at `trgm_op.c:528-533` (leading) and `:569-570`
  (trailing). `foo` -> `"  f"`, `" fo"`, `"foo"`, `"oo "` -- padded
  word-boundary grams, not a raw sliding window. Header notes `trgm_regexp.c`
  hard-codes these (`trgm.h:14-15`). VFS correct.

- **Multibyte trigrams CRC-hashed (lossy).** `compact_trigram`
  (`trgm_op.c:373-393`): a 3-*byte* trigram copied as-is, but any trigram
  spanning multibyte chars is reduced via `INIT/COMP/FIN_LEGACY_CRC32` keeping
  only the **3 upper CRC bytes** (lines 382-391; comment *"use only 3 upper
  bytes from crc, hope, it's good enough hashing"*). A trigram is a *character*
  triple (`make_trigrams:399-483` advances by `pg_mblen`), so non-ASCII code is
  hashed into a lossy 24-bit space -- collisions possible, raw bytes
  unrecoverable. VFS's raw-byte window deliberately avoids this. VFS correct.

- **`IGNORECASE` unconditional (case-folded only).** `trgm.h:25`, applied via
  `str_tolower(..., DEFAULT_COLLATION_OID)` (`trgm_op.c:541-545`). pg_trgm is
  *also* a single case-folded stream -- this part **agrees** with VFS's
  single-lowercase-stream choice (same precedent), but pg_trgm folds via
  collation-dependent `str_tolower` whereas VFS uses Unicode `casefold()`. VFS's
  fold is more correct (`ss`<-`ss`/sharp-s) and collation-independent.

### 4. pg_trgm regex -> trigram (informational; VFS query path out of scope)

`trgm_regexp.c:5-43` documents a 4-stage NFA->trigram compiler: (1) compile
regex to NFA; (2) expand NFA so each arc is labeled with a *color* trigram
(last-two-chars prefix + arc color); (3) expand color trigrams to character
trigrams, dropping/simplifying if too many; (4) pack into `TrgmPackedGraph`
evaluated by `trigramsMatchGraph`. Worked example (line 9):
`(ab|cd)efg => ((abe & bef) | (cde & def)) & efg` -- same AND/OR-over-required
-grams logic VFS's `build_code_gram_query` produces (`GramAnd`/`GramOr`/`GramAny`).

- **Lossy-but-sound by construction.** `trgm_regexp.c:11-16,53-58`: a matching
  string must satisfy the trigram expression, not vice-versa; false positives
  rechecked by the real regex. Byte-for-byte VFS's "false positives OK, false
  negatives forbidden, final regex enforces truth."
- **Hard cap -> degrade.** `MAX_TRGM_COUNT 256`, `WISH_TRGM_PENALTY 16`
  (`trgm_regexp.c:217-224`); past the ceiling pg_trgm fails the optimization.
  VFS's analog is collapsing to `GramAny`. Same escape hatch, different trigger.

### 5. "Elements never deleted" + concurrency

- **Entry-tree keys never deleted.** `README:313-314`: *"the greatest leaf tuple
  serves as high key. That works because tuples are never deleted from the entry
  tree."* GIN never removes a *gram* (entry-tree key) even with no live TID; only
  posting *contents* are vacuumed. Same property VFS relies on: a `gram_key`,
  once present, persists; deletes are tombstone deltas (latest-action-wins), only
  posting *contents* (doc-ids) are reclaimed by compaction.

- **fastupdate forces a coarse near-full-index lock at search time.**
  `README:501-508`: *"all scans grab a lock the metapage... with fastupdate=on,
  we effectively always grab a full-index lock, so you could get a lot of false
  positives."* VFS's staging table sidesteps this (ordinary row-level MVCC) -- a
  genuine advantage -- though VFS still pays the read-amplification of folding
  pending deltas, the same cost GIN pays scanning list pages (`README:99-102`).

- **Posting-tree page deletion is the hard concurrency case.** `README:340-474`:
  careful xid-marking + right-link stepping to delete posting-tree pages safely
  under concurrent readers. VFS's copy-on-write compaction (write new blocks,
  flip `is_active=false`, never mutate in place) is a *strictly simpler* model
  that avoids this entire class of problem -- a point in VFS's favor.

---

## Confirms / Contradicts

### Confirmed by source (VFS matches proven mechanics)

1. **Staging -> flush layering** = GIN pending list + `ginInsertCleanup`
   (`README:97-105`, `ginfast.c:448-471`). VFS's "exact tradeoff GIN's fastupdate
   makes" claim is accurate.
2. **Merge-on-read cost & inline-merge stall** both real in GIN: linear
   pending-list scans (`README:99-102`) and in-insert cleanup that "could take
   significant amount of time" (`ginfast.c:449-451`).
3. **work_mem vs maintenance_work_mem tiering** maps directly onto GIN
   (`ginfast.c:807-828`). Exact precedent to cite.
4. **Bounded immutable blocks + delta/varint** = GIN segmented posting lists
   (`README:269-304`, `ginpostinglist.c:114-127,214-226`). Cite constants
   `GinPostingListSegmentTargetSize 256` / `MaxSize 384`.
5. **No `pg_trgm` as the index** -- all four reasons confirmed (Findings 3):
   word padding (`trgm.h:16-17`, `trgm_op.c:528-570`), punctuation dropping
   (`trgm_op.c:337-366`, `trgm.h:50`), multibyte CRC hashing
   (`trgm_op.c:373-393`), unconditional case-fold (`trgm.h:25`,
   `trgm_op.c:541-545`). VFS correct to reject pg_trgm as the canonical index.

### Where VFS should borrow GIN specifics

A. **Size-based flush trigger.** GIN flushes at `gin_pending_list_limit`
   (default 4 MB, `guc_parameters.dat:1203`). VFS gives only "minutes/benchmarked"
   with no size bound. GIN deliberately uses *size* because read cost scales with
   pending size, not age. Document a default staging size cap (analogous 4-16 MB)
   alongside the time cadence.

B. **Inline-vs-promote in block terms.** GIN promotes at `GinMaxItemSize`
   (~1/3 page compressed, `ginblock.h:249-253`), targets 256-byte segments. VFS
   lists block sizes only as doc-id counts. Bound a block by **both** a doc-id
   count cap **and** an encoded-byte cap so a pathological gram can't make a giant
   block.

C. **Single-flight flush, mirroring GIN's conditional-lock backoff.** GIN's
   non-vacuum cleanup takes the lock *conditionally* and bails if another backend
   is cleaning (`ginfast.c:825`). VFS's flush/compaction must be single-flight +
   idempotent (one compactor per index; a second no-ops) so two compactors never
   race on one gram's blocks.

D. **First-item-uncompressed anchor.** GIN stores the first TID raw, deltas the
   rest (`ginpostinglist.c:215-224`). VFS already has `min_doc_id` in the block
   schema -- specify that `min_doc_id` *is* the delta anchor, matching GIN.

### Where VFS is simpler/better than GIN (keep, and say so)

- Copy-on-write blocks avoid GIN's posting-tree page-deletion concurrency dance
  (`README:340-474`).
- Ordinary-table staging avoids GIN's coarse metapage interlock (`README:501-508`).
- Unicode `casefold()` more correct than pg_trgm's collation `str_tolower`
  (`trgm_op.c:541-545`).

---

## Proposed edits (for the owner to apply -- NOT applied here)

### spec.md -> "Durable Storage Model" -> "Flush (staging -> posting blocks)"

After step 1 ("Close the current open batch..."), add:

> "Flush is triggered by a **size bound on pending staging**, not only by a
> timer -- read cost scales with pending size, not age. Postgres GIN uses exactly
> this: `ginInsertCleanup` fires when the pending list exceeds
> `gin_pending_list_limit` (default 4 MB; `ginfast.c:458-460`,
> `guc_parameters.dat:1203`). VFS's default staging cap is a benchmarked knob in
> the same order of magnitude; the time cadence is a secondary trigger."

### spec.md -> "Durable Storage Model" -> "Posting-block compression"

Replace:

> sorted int doc IDs -> delta (gap) encode -> varint encode -> optional zstd/gzip

with:

> sorted int doc IDs -> store min_doc_id uncompressed as the block anchor
>                    -> delta (gap) encode the rest from the anchor
>                    -> varint (7-bit, high-bit-continuation) encode
>                    -> optional zstd/gzip
>
> This is the same primitive Postgres GIN ships: first item stored raw,
> `delta = val - prev` for the rest, varbyte encoding
> (`ginpostinglist.c:114-127, 214-226`; GIN README "Posting List Compression").
> GIN bounds a segment to ~256 B (`GinPostingListSegmentTargetSize`,
> `gindatapage.c:34-35`) and stops at ~384 B; VFS bounds a block by **both** a
> doc-id count cap **and** an encoded-byte cap so one pathological gram cannot
> produce an oversized block. `min_doc_id` in the block schema *is* the anchor.

### spec.md -> "Compaction and merge policy"

Augment the "Synchronous compaction stalls the unlucky write" bullet:

> "GIN confirms this in source: its non-vacuum cleanup runs *inside the user
> insert* once the pending list trips the threshold and 'could take significant
> amount of time' (`ginfast.c:449-471`), mitigating by taking the cleanup lock
> *conditionally* and bailing if another backend is already cleaning
> (`ginfast.c:825`). VFS's flush/compaction job must likewise be **single-flight
> and idempotent** -- at most one compactor per index, a second attempt no-ops."

Augment the work_mem mention:

> "GIN sizes its two cleanup paths for exactly this reason: a foreground
> insert-triggered cleanup uses `work_mem`, the background vacuum/forced cleanup
> uses `maintenance_work_mem` (`ginfast.c:807-828`). VFS's 'frequent small flush
> vs. periodic large compaction' tiering is the same split."

### spec.md -> new subsection "Why immutable, copy-on-write blocks (vs. GIN posting-tree deletion)"

> Postgres GIN deletes posting-tree *pages* in place, forcing a careful
> xid-marking + right-link-stepping protocol to stay correct under concurrent
> readers (GIN README "Concurrency", ~lines 340-474). VFS avoids this class of
> bug: blocks are immutable and retired by `is_active=false` (copy-on-write), so
> in-flight readers stay correct and failure recovery is trivial -- a
> simplification GIN cannot make because its posting pages are mutable. GIN never
> deletes *entry-tree keys* at all (README:313-314); VFS's gram-key dimension is
> likewise append-only/tombstoned, removed only by full reindex.

### spec.md -> "Native/Portable Backend Matrix" (PostgreSQL) and Scope item 5

> "Confirmed in pg_trgm source: extraction is per-*word* (alphanumeric runs only
> -- `find_word`/`ISWORDCHR`, `trgm_op.c:337-366`, `trgm.h:50`), each word is
> blank-padded `LPADDING=2`/`RPADDING=1` (`trgm.h:16-17`, `trgm_op.c:528-570`),
> and multibyte trigrams are reduced to the 3 upper bytes of a CRC32
> (`compact_trigram`, `trgm_op.c:373-393`). So `foo|bar` indexes as words
> `foo`,`bar` -- the `|` and every trigram crossing it are lost."

### implementation.md -> Decisions -> "`pg_trgm` is not the index"

> "Validated against PostgreSQL source 2026-05-25: word-oriented tokenization
> (`trgm_op.c:337-366`, `ISWORDCHR=t_isalnum_with_len`, `trgm.h:50`), word
> padding `LPADDING=2`/`RPADDING=1` (`trgm.h:16-17`), and lossy multibyte CRC32
> hashing (`trgm_op.c:373-393`) all confirm pg_trgm drops exactly the
> punctuation/operator/multibyte information VFS's raw sliding byte trigrams
> preserve. See analysis-pg_trgm-gin.md section 3."

### spec.md §6 Phasing (Target) / §7 Rationale -- posting-block storage

> "Posting-block encoding follows GIN's primitive: `min_doc_id` stored
> uncompressed as the delta anchor, `delta=val-prev` for the rest, varbyte
> (7-bit continuation) -- `ginpostinglist.c:114-127,214-226`. Bound each block by
> **both** a doc-id count cap and an encoded-byte cap (GIN bounds segments at
> ~256/384 B, `gindatapage.c:34-35`). The flusher/compactor is single-flight and
> idempotent, mirroring GIN's conditional-lock backoff (`ginfast.c:825`)."
