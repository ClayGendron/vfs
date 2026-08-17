# SQLite FTS5 (raw agent findings)

Checkout: ~/Git/Repos/sqlite ext/fts5/. Format spec = header comment fts5_index.c:22-259 (no fts5fmt.html).

## 1. %_data shadow table
- Whole index in one (id INTEGER PK, block BLOB) table + %_idx(segid, term, pgno, PK(segid,term)) (fts5_index.c:6873-6882). FTS5 models the index as a paged file using a SQL table as page store.
- Record types (fts5_index.c:82-259): structure record (rowid 10, :262; per level nMerge + segments (segid, pgnoFirst, pgnoLast) :87-119; V2 sentinel 0xFF000001 :60-74; max 64 levels :56), averages (rowid 1), segment leaves, doclist-index pages (:198-225), tombstone hash pages (:227-259).
- Rowid packing fts5_dri: segid(16b)|dlidx(1b)|height(5b)|pgno(31b) = 53 bits (fts5_index.c:266-283). Payoff: segment pages contiguous → drop segment = one ranged DELETE (:370); sequential read = one cursor walk. Max 2000 segments (fts5Int.h:107).
- Leaf page: default pgsz 4050 (fts5_config.c:19 — just under SQLite's 4096 page), range 32..65536 (:28,933); approximate cap (fts5_index.c:4475,4549,4588); poslists split across pages at varint boundaries (:4586-4600).
- Leaf layout (fts5_index.c:160-196): 4-byte header (offset of first rowid; offset of footer); footer = delta varints of term offsets (self-indexing leaf); terms front-coded, first term on page stored whole (:4518-4525, 184-196).
- Term traversal: NO internal term pages of FTS5's own — %_idx IS the b-tree above the leaves: `SELECT pgno FROM %_idx WHERE segid=? AND term<=? ORDER BY term DESC LIMIT 1` (fts5_index.c:2675-2684); separator-key prefixes written per leaf-starting term (:4279-4297, 4492-4515). Cost per term per segment: 1 %_idx row + 1 %_data blob + sequential follow.
- Doclist-index (dlidx): first rowid per spanned termless page, built only when term spans ≥ FTS5_MIN_DLIDX_SIZE=4 termless leaves (fts5_index.c:49, 4258-4262; format :198-225).
- I/O: sqlite3_blob_open/reopen, one round trip per leaf; blobs zero-padded 8/20 B on read vs overread (:288-290).

## 2. Doclist format (fts5_index.c:129-159)
- doclist = absolute first rowid + poslist, then (rowid delta>0 + poslist)*; 0 free as terminator; ABSOLUTE RESTART at each page start (:4566-4573) → pages independently decodable.
- poslist size field = n*2 + bDel (low bit = tombstone flag; empty poslist + size 1 = delete marker; :4869-4874; fts5_hash.c:199-212). collist offsets biased +2 so 0x00/0x01 free as sentinels.
- detail=full/col/none (fts5Int.h:285-287): full = rowid+col+offset; columns = rowid+col; none = pure delta-varint rowid list — LITERALLY vfs's format. detail=none merge path = fts5MergeRowidLists, ~30-line delta-varint merge (selected at :6708-6716).
- Documented sizes (fts5.html §4.6): 1636 MiB email corpus → 743 MiB full (45%), 340 MiB column (21%), 134 MiB none (8.2%). Positions premium 5.5× over rowid-only; columns 2.5×.
- Capability ladder: full = phrase/NEAR/positions; columns = boolean + column filters (fts5_expr.c:2417-2427 refuses phrase/NEAR); none = boolean only (:2237-2241 refuses column queries).
- ESCAPE HATCH = vfs's architecture, shipped: detail!=full answers position-needing aux functions by re-fetching the row and re-tokenizing (fts5_main.c:2331-2352); contentless short-circuits to empty (:2324-2329).
- Trigram tokenizer in-tree (fts5_tokenize.c:1275-1420, registered :1467): LIKE/GLOB acceleration; xBestIndex claims pattern (fts5_main.c:525-539); MATCH superset contract (fts5_expr.c:358-361); detail=none degrades phrase to AND of trigrams (:415-419); pattern constraint never sets omit=1 (fts5_main.c:678-685) → core re-evaluates real LIKE on every candidate. Index = filter; verification = full value. vfs = FTS5-trigram + detail=none + external verification.

## 3. Prefix indexes
- Separate parallel index per prefix length; 1-byte index-number prefix on terms (FTS5_MAIN_PREFIX '0', fts5_index.c:51); each token written (1+nPrefix)× (sqlite3Fts5IndexWrite fts5_index.c:6973-7002); max 31 (fts5Int.h:102). Query still merges all matching terms — index shortens the range scanned. Docs §4.2: space-for-time vs range scan abc..abd. No analogue for fixed-length grams.
- WARNING: fts5SetupPrefixIter materializes the fully merged doclist in memory (fts5_index.c:6682-6770; fan-in 16 lists :6165,6713) — don't copy for common grams; stream instead.

## 4. Maintenance = LSM with level bookkeeping in one SQL row
- Write: in-memory hash (fts5_hash.c:238-380; iSzPoslist back-patch :194-233); flush at 1 MiB default (fts5_config.c:23) or rowid regression (fts5_index.c:6788-6794); fts5FlushOneHash writes ONE new level-0 segment (:5594-5800); then automerge, crisismerge, structure write (:5796-5798). One commit ⇒ one new segment ⇒ zero rewriting.
- automerge (fts5_index.c:5020-5038): work counter crossing 64-page units → 64×nLevel pages of merge work; nAutomerge default 4 (fts5_config.c:20). Picks level with most inputs (:4964-5008).
- Incremental merge RESUMABLE (fts5IndexMergeLevel :4763-4912): resume state = pLvl->nMerge in structure record; budget exhausted → fts5TrimSegments truncates consumed prefix of inputs (:4906); clean EOF → remove inputs (:4880-4890). Delete-marker annihilation at oldest level (:4848).
- crisismerge: unbounded blocking backstop at 16 segments/level (fts5_index.c:5040-5055; default fts5_config.c:22); docs: "may take a long time."
- usermerge/'merge' command (:5930-5950); optimize work unit 1000 pages (:46, 5915). Deletes: re-read old row + re-tokenize to emit tombstones (fts5_storage.c:497-560); secure-delete = ~250 lines in-place blob surgery (fts5_index.c:5239-5470+); contentless_delete = per-segment tombstone hash pages + deletemerge 10% GC (fts5_index.c:227-259, 4920-4958; fts5_config.c:25).
- Query-time merge: implicit loser tree aFirst[] over N segment iterators, log(N) repair per advance (fts5_index.c:621-640, 3242-3270).

## 5. Content modes
- eContent NORMAL/NONE/EXTERNAL/UNINDEXED (fts5Int.h:280-283). Fetch via SELECT-by-rowid (fts5_storage.c:103) for: column values, positions when detail!=full, columnsize=0, delete-marker computation, rebuild/integrity-check. Answered from index alone: rowid, MATCH, bm25 (averages + %_docsize), and (full only) positions/snippets.
- Contentless losses: no UPDATE/DELETE (without contentless_delete), columns read NULL, 'delete' command needs caller to re-supply exact original values; detail!=full + contentless → xInst etc. return 0/EOF (fts5_main.c:2324-2329). Rationale §4.4: column values usually much larger than index entries.

## 6. Numbers table
pgsz 4050 (32..65536); index/content 45%/21%/8.2% (full/col/none); automerge 4 (max 16); crisismerge 16; usermerge 4 (2-16); deletemerge 10%; work unit 64 pages; optimize unit 1000; hash flush 1 MiB; dlidx threshold 4; segments ≤2000, segid ≤65535; levels ≤64; prefix ≤31; token ≤32768; fan-in 16; blob padding 8/20 B.

## Draft verdicts (agent's)
A. Paged segment btree in blobs — adaptable. DIRECT: "%_idx pattern" = let the SQL PK be the internal nodes (vfs already there with (epoch, gram)). ADAPTABLE: chunk oversized postings across rows (epoch, gram, seq)→blob with absolute-first-docid restart per chunk (TOAST/LOB thresholds: PG ~2KB TOAST whole-datum decompress, Oracle >4000 B off-row locator round trip, MSSQL varbinary(max) off-page). DOA: 4KB pages at one round trip each (in-process assumption) — vfs needs fewer, larger rows fetched set-wise (IN-list, ordered, streamed); chunks order of magnitude larger than 4KB. DOA: packed-rowid trick (keep real columns).
B. Skip structure — DIRECT and cheaper than FTS5: put first_doc/last_doc/n_docs as COLUMNS on posting chunk rows → "skip this chunk" is a SQL predicate, no blob shipped; intersect on chunk ranges before decoding. Threshold instinct: no skip metadata for single-chunk grams.
C. Poslists — DOA as designed (5.5× to answer what regex verification answers anyway; FTS5 itself ships vfs's fallback as supported). ADAPTABLE middle tier: detail=column ≈ 2.5× buys rejection without reading; vfs analogue = CHUNK LOCALITY — store chunk ordinal(s) per docid so verification fetches only matching chunks. "Highest-leverage transferable idea in the whole study." Steal byte-level: n*2+flag size field; +2 bias reserving 0x00/0x01.
D. Incremental merge — DOA for posting data (epoch swap already beats it: atomic visibility, no delete markers, no crisismerge latency cliff, no per-segment query cost). DIRECT: structure record = epoch pointer done well — copy (1) format-version sentinel that old readers fail loudly on (:60-74), (2) monotone write counter to amortize/trigger background work (:98, 5027-5033) → vfs: track scan-tier absorption since last epoch as rebuild trigger. Also: resumable-rebuild checkpoint in epoch metadata (nMerge discipline, :4787-4827). Warning: never materialize a common gram's postings whole — streaming k-way merge with early termination (aFirst[] pattern).
