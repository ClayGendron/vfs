# PostgreSQL GIN + pg_trgm (raw agent findings)

Checkout: ~/Git/Repos/postgres @ 377cc45194f4.

## 1. Posting storage
- Two-level: entry B-tree over keys → per-key inline posting list OR posting tree (B-tree over TIDs) (src/backend/access/gin/README:22-26, 95-105).
- No delete from entry tree ever — vocabulary near-stationary (README:28-31; vacuum removes TIDs, never keys — README:391-396).
- Inline list cap = GinMaxItemSize ≈ page/3 ≈ 2704 B @ 8kB (ginblock.h:249-253, comment :242-248). Spill decision = "try to encode; if nwritten != n, createPostingTree" (gininsert.c:247-284 addItemPointersToLeafTuple; :309-338 buildFreshLeafTuple). Once a tree, always a tree (gininsert.c:375-388). Tuple-header encoding of which case (README:151-188).
- COMPRESSED SEGMENTS, the key design point (README:269-275): items stored as many independent segments, not one big list — skip to the segment containing the item, decode only it; updates re-encode one segment. Sizes: min 128 / target 256 / max 384 B; MinTuplesPerSegment=63 (gindatapage.c:25-43; split/merge in leafRepackItems gindatapage.c:1571-1734).
- Varbyte delta encoding (README:277-304; ginpostinglist.c:23-72, 114-183, 196-277 ginCompressPostingList, 297-352 decode). ItemPointer packed to 43 bits (11-bit offset), ≤6 bytes.
- INVARIANT worth stealing (ginpostinglist.c:55-71, with proof): removing an item from a delta-varint list never increases encoded size → vacuum can rewrite in place. Deletion in-place-safe; insertion not — hence pending list for inserts, vacuum for deletes.
- ginMergeItemPointers (ginpostinglist.c:377-434): sorted merge + dup elim, memcpy fast path for non-overlapping ranges.
- Decode-to-bitmap fast path: ginPostingListDecodeAllSegmentsToTbm (ginpostinglist.c:357-369).

## 2. fastupdate pending list (analog of vfs scan tier)
- Shape: unsorted chain of full pages off metapage (head/tail/nPendingPages), one index tuple per (key, TID), no posting lists (README:201-216). GIN_LIST_FULLROW marks whole-row pages.
- Insert: ginHeapTupleFastCollect (ginfast.c:483-545) + ginHeapTupleFastInsert (ginfast.c:218-472) — append to tail page free space or splice fresh sublist (makeSublist :144-209). No sorting, no descent.
- Search: gingetbitmap calls scanPendingInsert BEFORE startScan, unconditionally (ginget.go... ginget.c:1960). ORDERING IS LOAD-BEARING (ginget.c:1950-1959): scan pending first or concurrent cleanup makes you miss entries; duplicate visits fine (bitmap set twice), a miss is not. (Also why GIN can't do amgettuple.)
- scanPendingInsert (ginget.c:1836-1925) walks pages linearly; per heap row runs full consistent evaluation (:1902-1912); within a row, binary search over the row's sorted entries (ginget.c:1662-1699). Cost linear in overlay rows, no cross-row pruning.
- Concurrency: predicate lock on metapage per scan (ginget.c:1851-1855); README:501-508 "effectively always grab a full-index lock... lot of false positives" (serializable).
- Flush (ginInsertCleanup, ginfast.c:779-1025):
  - LockPage metapage exclusive; ordinary insert uses ConditionalLockPage and BAILS if someone else is cleaning (ginfast.c:807-828) — foreground cleanup best-effort, no convoy.
  - Memory: maintenance_work_mem when from vacuum, work_mem when piggybacked (ginfast.c:813-827).
  - Records blknoFinish = tail at start — drains only the snapshot seen at start; bounded under sustained writes (ginfast.c:843-847, :887-888).
  - Uses same bulk path as index build (ginEntryInsert via BuildAccumulator; processPendingPage ginfast.c:708-763).
  - Re-check for appends during unlock (ginfast.c:943-961); shiftList unlinks ≤16 pages/WAL record (ginxlog.h:205).
  - Crash-safe by idempotence (ginfast.c:767-772): merge-then-unlink; crash between = redundant re-post, never loss.
- Triggers: (1) size at insert time: nPendingPages * GIN_PAGE_FREESIZE > gin_pending_list_limit → cleanup outside critical section; deliberately fires while list still fits so one collection cycle suffices (ginfast.c:448-471, comment :449-455). (2) vacuum (ginvacuum.c:630, :746, :759). (3) autoanalyze (ginvacuum.c:738-749). (4) manual gin_clean_pending_list() (ginfast.c:1030-1091).
- Knob: gin_pending_list_limit default 4MB, min 64kB, per-index override (guc_parameters.dat:1199-1206; reloptions.c:380-386; gin_private.h:41-47). fastupdate default ON (gin_private.h:35).
- Documented tradeoff (doc/src/sgml/gin.sgml:525-533): "a large list of pending entries will slow searches significantly... an update that causes the pending list to become too large will incur an immediate cleanup cycle." Escape hatch :535-541: turn fastupdate off when consistent response time matters. Sizing guidance :599-621: prefer background cleanup (autovacuum); raising the cap = rarer but longer foreground stall. :570-586: for bulk loads, drop + recreate index — past some batch size wholesale rebuild beats incremental merge (= vfs's posture).
- Cost accounting (selfuncs.c): nPendingPages read LIVE from metapage, trusted; other stats stale (:8682-8696). ENTIRE pending list charged as startup cost before any entry-tree work (:8851-8855).

## 3. pg_trgm
- Padding LPADDING 2 / RPADDING 1 (trgm.h:16-17); IGNORECASE compile-time fold (trgm.h:18-25); words = alnum runs only (trgm.h:50; trgm_op.c:337-366); str_tolower with DEFAULT collation (trgm_op.c:545); trigram = exactly 3 bytes, multibyte hashed via CRC32 top 3 bytes — lossy, collisions accepted because recheck cleans up (compact_trigram trgm_op.c:373-393; make_trigrams :398-483). generate_trgm sorts+dedups — set not multiset, no positions/counts (trgm_op.c:598-620). GIN key = int32 (trgm_gin.c:59-62).
- LIKE → AND-set of trigrams from literal fragments, padded only on non-wildcard sides (generate_wildcard_trgm trgm_op.c:1088-1154; get_wildcard_part :1000-1079; gin_trgm_consistent trgm_gin.c:228-240).
- Regex → NFA → color-trigram graph (trgm_regexp.c:1-190 header = design doc): 4 stages; lossy at every stage (drop color trigrams and merge states when too many, penalty table favoring low-whitespace trigrams :231-240; limits MAX_EXPANDED_STATES 128, ARCS 1024, MAX_TRGM_COUNT 256, WISH_TRGM_PENALTY 16 :211-225). Evaluation = graph reachability (trigramsMatchGraph :627+), not boolean AND; same graph pointer in every extra_data slot (trgm_gin.c:120-131). No extractable trigrams → GIN_SEARCH_MODE_ALL full scan (trgm_gin.c:134-138; pgtrgm.sgml:551-556). triconsistent promotes MAYBE→true (monotonic fn, trgm_gin.c:340-344).
- Recheck UNCONDITIONAL for all strategies (trgm_gin.c:187-188).

## 4. GIN lossy semantics
- Bitmap-only (amgettuple NULL, ginutil.c:85-86; reason: pending list may be visited twice, ginget.c:1955-1956).
- Recheck sources: opclass GIN_MAYBE (ginget.c:1264-1276); page lossification (ginget.c:1200-1214, 1974-1975); OR over keys (:1433-1443). Executor re-evaluates original qual on fetched heap tuple (nodeBitmapHeapscan.c:196-210). Contract: indexam.sgml:943-951 (lossy index, core re-applies conditions).
- Structurally identical to vfs: one-sided guarantee, arbitrary lossiness licensed, degradation to "everything" affects cost not correctness, recheck = per-result OR.

## 5. Numbers table
- Inline cap ~2704 B; segments 128/256/384 B; 63 min tuples/seg; ItemPointer 43 bits ≤6 B; pending limit 4MB default / 64kB min; ≤16 pages unlinked per WAL record; regex limits 128/1024/256/16; padding 2+1; gin_fuzzy_search_limit 5000-20000 "works well" (gin.sgml:638-655, README:57-81).

## Draft verdict (agent's)
Pending list validates vfs's scan-tier overlay; adopt: (1) overlay-first scan order + set-union (stated invariant, not statement-order accident); (2) bounded merge via snapshot fence at start; (3) merge-then-unlink idempotent publish (epoch blobs visible BEFORE overlay watermark advances); (4) two triggers — background cadence + size backstop, size trigger conditional/non-blocking (bail if rival merging); (5) fire size trigger BELOW cap; asymmetric memory budgets; (6) charge overlay as startup cost, read its size live, let it gate plan choice (past some overlay size, scan-everything wins). Cap expressed in DOCUMENTS not bytes (cost linear in docs); derive from target added latency. Consider overlay-disabled synchronous mode (fastupdate=off analog). Also: store the extracted sorted gram set per changed doc at write time so overlay probes are merges, not re-extractions (pending list's data shape).
Segments: YES — segment the gram blob (length-prefixed, each restarting at absolute docid) for skip-ahead intersection + early termination; tune segment size to decode cost, not 8kB pages. Deletion invariant → in-place tombstoning of deletes between rebuilds is a real option (deletes shrink, inserts grow — absorb deletes in place, defer inserts to overlay).
Posting trees: NO — they exist for page granularity + concurrent in-place insertion + vacuum under concurrency; vfs's analog if a blob exceeds limits is flat row chunking (gram, chunk_no) → blob, spill decided by try-to-encode size test.
Steal outright: stable gram keyspace across rebuilds — UPDATE payloads rather than DELETE+INSERT rows; epoch bump = payload swap not table swap (README:28-31 rationale).
