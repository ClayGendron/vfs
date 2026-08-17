# Field study: how search systems organize storage to avoid fetching whole documents — and what maps onto SQL rows

Prior-art research memo, design input only. Sources: source-level study of read-only
checkouts under `~/Git/Repos/` (zoekt, codesearch, sqlite/ext/fts5, postgres,
seaweedfs, juicefs) plus public design writing (cited by URL). Every design described
here is described, not prescribed; every line of vfs stays ours. Per-system raw notes
with full cite lists live beside this file (`notes-*.md`).

## vfs ground truth this memo is calibrated against

- Postings are `gram → delta+varint blob of doc ids`, where doc ids are **entry**
  surrogate row ids; gram extraction is entry-grain over the full folded body, and
  the chunks table is semantic-only — "no gram-path code reads them"
  (`src/vfs/storage/backends/database/indexing.py:15-24`,
  `src/vfs/models/postings.py:1-16`).
- Verification fetches **whole bodies** from the content table per candidate
  (`_content_for_entries`, `src/vfs/storage/backends/database/grep.py:681-689`).
- The index is case-folded at build time ("plan folded grams unconditionally",
  `grep.py:4-5`); published by CAS epoch-pointer flip + per-entry `encoded` flags;
  recently-changed docs are served by the `NOT encoded` scan overlay
  (`grep.py:1-17`, `indexing.py:1-14`).
- Posting rows already carry `doc_count` and `byte_size` metadata columns
  (`_posting_meta`, `grep.py:447-460`).
- Measured cost order on the linux-tree corpus: candidate content fetch bytes ≫
  result assembly ≫ gram decode+intersect; ~3–5 ms per-call floor. A 3-segment-scope
  query fetches ~200 MB of bodies for ~2.5k matching lines.

---

## 1. Zoekt — positional trigram postings (Apache-2.0; `~/Git/Repos/zoekt`)

### Findings

**Postings are positions, not doc ids.** Each trigram's posting list is a
delta+varint sequence of corpus-global rune offsets — the offset of every
*occurrence*, monotone across the shard's concatenated documents
(`index/shard_builder.go:214` computes `newOff = endRune + runeIndex - 2`;
`:238-247` varint-appends deltas, with a single-byte fast path — "~80% of deltas
are < 128"). No count prefix since format v6 (`index/toc.go:20`); the blob is pure
deltas with an absolute first value (`index/hititer.go:188-196`).

**Two-level section structure.** The shard file is a TOC of `simpleSection`
(off, sz byte range — `index/section.go:101-134`) and `compoundSection` (data range
plus a per-item uint32 offset index — `:136-170`); the TOC is written last with a
trailing 8-byte pointer (`index/write.go:239-245`). `writePostings`
(`index/write.go:81-125`) emits, in ngram-sorted order: the `ngramText` array
(three 21-bit runes packed in a uint64, `index/bits.go:82-84`), the postings
compound section, `runeOffsets`, and `fileEndRunes`. Ngram lookup is a B+-tree
whose inner nodes live in RAM and whose leaves are the mmap'd `ngramText` section,
one 8 KB page-shaped bucket of 1024 ngrams per leaf (`index/btree.go:47, 314-352`);
resolving a posting list reads just two uint32s from the posting index
(`:359-397`). The posting section's *byte size* doubles as the trigram frequency,
read without touching the blob (`index/indexdata.go:437, 442`).

**How positions limit verification.** For a substring atom, zoekt picks the **two
lowest-frequency trigrams** of the pattern (`findSelectiveNgrams`,
`index/indexdata.go:337-383`) and merges just those two posting lists under the
constraint `p1 + runeDist == p2`, where `runeDist` is the trigrams' distance inside
the pattern (`distanceHitIterator.findNext`, `index/hititer.go:51-69`). A candidate
is therefore not a document — it is an *exact corpus offset where the pattern could
start*. Offsets resolve to documents by galloping search over the `fileEndRunes`
boundary array (`index/matchiter.go:132-147`), and hits that would straddle a
document boundary are rejected by the pattern's left/right padding
(`:199-201`). Verification for substring atoms is then `bytes.Equal` (or a
case-folding compare) over `content[off : off+len]` — no scan, no regex engine at
all (`index/matchiter.go:50-68`, `index/matchtree.go:958-989`). Cost per candidate:
O(pattern length).

Two honest caveats. First, `cp.data()` does hand back the *whole document* as a
zero-copy mmap slice (`index/contentprovider.go:81-92`); only the pages around the
offset actually fault in, and the `ContentBytesLoaded` stat overstates true I/O
(`:89`). The only genuine byte-range read in the code is
`readContentSlice(byteOff, 300)` (`index/read.go:531-538`). Second, **regex atoms
still scan whole documents** (`regexpMatchTree.matches` runs `FindAllIndex` over
the full body, `index/matchtree.go:810-845`) — positions gate *which* documents
reach the regex, via the cost ladder `costConst < costMemory < costContent <
costRegexp` (`index/matchtree.go:51-61`, `index/eval.go:276-289`). The exception
is `andLineMatchTree` (`index/matchtree.go:681-765`): for regexes classified
single-line at plan time (`eval.go:610-676`), candidate offsets are mapped to lines
via the newline index and merge-joined; a doc with no single line containing all
terms is rejected **without running the regex**.

**Size overhead (documented).** "The index is large. Empirically, it is about 3x
the corpus size, composed of 2x (offsets), and 1x (original content)"
(`doc/design.md:66-70`); in practice ~3.5x (`doc/design.md:145-146`,
`doc/faq.md:112-114`). So positional postings ≈ **2x corpus, ~57% of the shard** —
versus codesearch's ~0.2x for docid-only. The accepted rationale: only *two*
posting lists are read per atom, so postings can live on SSD and only ~1.2x corpus
of RAM is needed (`doc/design.md:56-64, 79-81`). Bloat is bounded by hard gates:
2 MB per-file cap, 20,000 distinct trigrams per doc, binary-file skip
(`index/builder.go:325-333`, `index/shard_builder.go:680-720`).

**Case-insensitivity: query-side expansion, no folded copies stored**
(`doc/design.md:92-98`). `generateCaseNgrams` walks `unicode.SimpleFold` over the
three runes — ≤8 variants (`index/bits.go:26-47`); one posting blob is read per
variant and the hit streams unioned (`index/hititer.go:115-146, 232-267`);
verification compares case-foldingly at the offset only (`index/matchiter.go:56-67`).
Cost: ≤8× lookups per trigram, zero storage.

**Line-number resolution without content.** Per document, a small delta-varint blob
of the byte offset of every `\n` (`index/write.go:137-141, 259-267`), read on
demand and cached; offset→line is a binary search, and a line's byte range — hence
its text — comes from two adjacent entries (`index/contentprovider.go:460-514`).
The `fileEndRunes`/`boundaries` arrays give offset→doc and doc sizes in O(1)
(`index/read.go:287-288, 377`). A separate sampled rune→byte correction map
(`index/bits.go:342-402`) exists only because zoekt indexes rune offsets — an
apparatus (plus a 300-byte content read per candidate) that a byte-offset design
simply deletes, as zoekt's own `PlainASCII` short-circuit hints
(`index/contentprovider.go:98-100`).

### Maps to vfs how

- **Direct**: the positional posting *encoding* (identical delta+varint blob shape
  vfs already ships); two-trigram distance intersection (reads *fewer* posting
  bytes — two blobs per atom — while collapsing candidates to exact offsets);
  posting `byte_size` as the selectivity signal (vfs already stores it); sorted,
  batched gram lookups; query-side case expansion (vfs currently folds at build
  time — zoekt shows the alternative and its price, ≤8× lookups vs. index-side
  fold; vfs's current folded index is also fine, this is a design choice not a
  defect); per-doc newline-index blob; cost-ladder evaluation order (vfs's gate
  ordering already approximates it).
- **Adaptable**: verification against a byte *range*. Zoekt gets ranges for free
  from mmap; the SQL translation is "candidate offset → the covering content
  chunk rows," which requires content to be fetchable by `(doc, offset range)` —
  see §8. Offsets should be per-doc byte offsets (`(doc, off)` pairs, doc-major
  delta-encoded), not corpus-global rune offsets: corpus-global numbering would
  have to be re-minted every epoch, and rune offsets exist only to serve
  unicode-fold semantics a byte-exact Rust verifier does not need.
- **Dead on arrival**: mmap/"content lives in the index" (the whole-doc
  `cp.data()` call shape *is* vfs's 200 MB symptom when replayed over a DB
  connection); the in-process ngram B+-tree (the SQL PK on `(epoch, gram)` already
  is it); uint32/4 GB shard caps (vfs must not design toward a scale cap).

---

## 2. codesearch / Russ Cox — the design vfs currently mirrors (BSD-3; `~/Git/Repos/codesearch`)

### Findings

The index is exactly what vfs has: `trigram → sorted delta-coded docid list`, no
positions, no counts — the posting payload is γ-coded deltas ending in a zero
delta (`index/read.go:31-46`; v1 used uvarint, `:100-108`). A posting entry is a
packed `trigram<<40 | fileid` uint64 with no room for anything else
(`index/write.go:100-123`), and postings are set-valued per file — one entry per
*distinct* (trigram, file) (`index/write.go:286-293`), so the index cannot even
count occurrences. The planner compiles a regexp into a conservative AND/OR
trigram query ("it matches everything the regexp would match, and probably quite
a bit more", `index/regexp.go:14-21`); evaluation returns `[]int` file ids
(`index/read.go:561-615`); and verification opens each candidate and runs the DFA
over the **entire file** in 1 MB chunks with no seek and no positional hint
(`cmd/csearch/csearch.go:147-189`, `regexp/match.go:432-549`).

Cox's article (swtch.com/~rsc/regexp/regexp4.html, Jan 2012) states the positional
tradeoff — one section before declining it. On phrase search: "Storing the
position information in the index entries makes the index bigger but **avoids
loading a document from disk unless it is guaranteed to be a match**"; the
alternative (AND query + load bodies + filter) is "unattractive" for common-word
phrases. For the trigram index he then chooses docids-only and never revisits —
the stated virtues are index size ("the index tends to be around 20% of the size
of the files being indexed... indexing the Linux 3.1.3 kernel sources, a total of
420 MB, creates a 77 MB index") and simplicity ("under 500 lines of code"). His
precision numbers are excellent (Datakit: 2,739 → 3 files, all matches; "hello
world" on Linux: 36,972 → 25 files, ~100x), and his verification cost model is
mmap + OS page cache — bodies are assumed ~free to read. Format-size ground
truth from the repo: on a linux tree, docid postings alone are ~94% of the index
(147.7 MB of 157.8 MB, `index/read.go:113-124`).

### Maps to vfs how

**This is vfs's current organization, so the verdict is a diagnosis, not a
transfer.** The cost codesearch knowingly accepts — fetch and scan the entire body
of every candidate, including the non-matching remainder of every true positive —
is precisely the cost vfs measures as dominant. It stays invisible in csearch only
because candidate bodies come from the local page cache; vfs pays a SQL round trip
and full transfer instead, so the term Cox's model treats as free is vfs's whole
bill. Corollary that bounds future optimization work: **improving planner
precision cannot fix this** — Cox's own numbers show precision is already near its
ceiling, and a zero-false-positive planner still transfers every true candidate's
full body. The lever codesearch declined (positions, argued for by Cox himself in
the phrase paragraph) is the lever that attacks vfs's measured bottleneck.

---

## 3. SQLite FTS5 — the existing proof of a posting index in SQL btree rows (`~/Git/Repos/sqlite/ext/fts5`)

### Findings

**The whole index lives in one `(id INTEGER PRIMARY KEY, block BLOB)` table**
(`%_data`), plus `%_idx(segid, term, pgno, PRIMARY KEY(segid, term))`
(`fts5_index.c:6873-6882`). FTS5 does not model its index in SQL; it models it as
a paged file and uses a SQL table as the page store. Rowids pack
`segid|dlidx|height|pgno` into 53 bits (`fts5_index.c:266-283`) so a segment's
pages are contiguous — dropping a merged-away segment is one ranged `DELETE`
(`:370`). Leaves default to 4050 bytes — deliberately just under SQLite's 4096
page (`fts5_config.c:19`) — self-index their terms via a footer of delta varints,
and front-code terms within a page (`fts5_index.c:160-196, 4518-4525`).

**Term lookup delegates the b-tree's internal nodes to SQL.** There are no
internal term pages: the lookup is `SELECT pgno FROM %_idx WHERE segid=? AND
term<=? ORDER BY term DESC LIMIT 1` (`fts5_index.c:2675-2684`), with shortest
separator-key prefixes written one row per leaf-starting term (`:4492-4515`). One
term in one segment costs 1 `%_idx` row + 1 blob row. For doclists spanning many
termless leaves there is a doclist-index (first rowid per spanned page), built
only when a term spans ≥4 termless leaves (`fts5_index.c:49, 198-225,
4258-4262`).

**Doclist format** (`fts5_index.c:129-159`): absolute first rowid, then
`(rowid delta > 0, poslist)*` — zero is the terminator, and **deltas restart at an
absolute rowid on every page** (`:4566-4573`), which is what makes pages
independently decodable. The poslist size field is `n*2 + delete-flag` (the low
bit is a free tombstone channel), and position offsets are biased +2 so 0x00/0x01
serve as sentinels. `detail=` is a granularity dial (`fts5Int.h:285-287`):
`full` = rowid+column+token offset; `col` = rowid+column; `none` = a pure
delta-varint rowid list — **literally vfs's posting format**, whose entire merge
algebra in FTS5 is a ~30-line sorted delta-varint merge (`fts5MergeRowidLists`,
selected at `fts5_index.c:6708-6716`). Documented sizes (fts5.html §4.6): a
1636 MiB corpus indexes to 743 MiB full / 340 MiB col / 134 MiB none — i.e.
**45% / 21% / 8.2% of content, so positions cost 5.5× rowid-only and the middle
tier 2.5×**. What each still answers: full = phrase/NEAR/positions; col = boolean
+ column filters (`fts5_expr.c:2417-2427`); none = boolean only (`:2237-2241`).

**FTS5 ships vfs's architecture as a supported mode, twice over.** With
`detail!=full`, position-requiring functions are answered by re-fetching the row
and re-tokenizing on the fly (`fts5_main.c:2331-2352`). And the in-tree trigram
tokenizer (`fts5_tokenize.c:1275-1420`) accelerates LIKE/GLOB by compiling the
pattern to a MATCH over a **superset** of matching rows (`fts5_expr.c:358-361`;
under detail=none the phrase degrades to an unordered AND of trigrams,
`:415-419`) while never setting `omit=1` on the constraint
(`fts5_main.c:678-685`) — SQLite core re-evaluates the real LIKE against every
candidate's full value. Index = filter, verification = full value: vfs is
FTS5-trigram + detail=none with the verifier moved out of SQLite.

**Maintenance is an LSM with its level bookkeeping in one SQL row.** Each commit
flushes the in-memory hash (1 MiB default) as one new level-0 segment — zero
rewriting of existing segments (`fts5_index.c:5594-5800`). `automerge` amortizes:
every 64 leaf pages written buys `64 × nLevel` pages of background merge
(`:5020-5038`); `crisismerge` (16 segments/level) is the unbounded blocking
backstop, documented as a latency cliff; merges are *resumable* — budget
exhaustion truncates the consumed prefix of the inputs and records `nMerge` in
the structure record so the next call continues (`:4763-4912`). The structure
record itself (rowid 10) is one small row naming the live segment set, with a
format-version sentinel chosen so old readers fail loudly (`:60-74`) and a
monotone write counter that drives the amortization (`:98, 5027-5033`). Deletes
are the ugly corner: re-tokenize the old row to emit tombstones
(`fts5_storage.c:497-560`), or ~250 lines of in-place blob surgery
(`secure-delete`), or per-segment tombstone hash pages + a `deletemerge` GC
heuristic.

**Prefix indexes** are parallel full indexes (each token written 1+nPrefix times,
`fts5_index.c:6973-7002`) — no analogue for fixed-length grams. One warning to
carry: the prefix-query path materializes the fully merged doclist in memory
(`fts5SetupPrefixIter`, `:6682-6770`); the streaming loser-tree used for normal
query-time merges (`:621-640`) is the right pattern instead.

### Maps to vfs how

- **Direct**: the `%_idx` lesson — let the SQL PK be the b-tree's internal nodes
  (vfs's `(epoch, gram)` PK already is; do not hand-roll separator pages). The
  skip-structure idea, *improved* by SQL: put `first_doc`/`last_doc`/`n_docs` as
  columns on posting chunk rows so "skip this chunk" is a WHERE predicate
  evaluated without shipping the blob. The structure-record discipline for vfs's
  epoch pointer row: a format-version sentinel old readers refuse loudly, and a
  monotone absorption counter (docs/bytes taken by the scan overlay since last
  epoch) as the rebuild trigger — FTS5's automerge idea re-expressed for
  wholesale rebuilds. Resumable-rebuild checkpoints in epoch metadata. The
  byte-level tricks (`n*2+flag` size field; +2 bias freeing 0x00/0x01).
- **Adaptable**: multi-row posting chunking `(epoch, gram, seq) → blob` with an
  absolute-docid restart per chunk — motivated off SQLite by LOB thresholds (PG
  TOAST decompresses whole datums; Oracle >4000 B goes off-row behind a locator;
  MSSQL `varbinary(max)` overflows off-page). But chunk at 10–100× FTS5's 4 KB:
  FTS5 affords a round trip per 4 KB leaf only because SQLite is in-process. The
  `detail=column` middle tier translated: vfs's analogue of "column" is **chunk
  ordinal** — a coarse locality tag per posting at ~2.5× rowid-only cost instead
  of 5.5× for exact offsets (see shortlist).
- **Dead on arrival**: the LSM merge apparatus for posting data (epoch-wholesale
  swap already provides atomic visibility with no delete markers, no crisismerge
  cliff, no per-segment query cost — FTS5's delete machinery is the strongest
  argument *for* vfs's rebuild-and-swap); per-4KB-page I/O; the packed-rowid
  trick (vfs has real columns and real ranged deletes).

---

## 4. PostgreSQL GIN + pg_trgm — posting segments and the pending list (`~/Git/Repos/postgres`)

### Findings

**Layout.** An entry B-tree over keys; per key, either an inline compressed
posting list (cap ≈ page/3 ≈ 2704 B) or, when "try to encode" overflows, a
posting *tree* (`src/backend/access/gin/README:22-26`; `ginblock.h:249-253`;
`gininsert.c:247-338`). The entry tree **never deletes keys** — vocabulary is
near-stationary (`README:28-31`). Posting data is varbyte delta-encoded
ItemPointers packed to 43 bits (`ginpostinglist.c:23-72`), stored as **many
independent segments** (min/target/max 128/256/384 B, `gindatapage.c:25-43`)
precisely so a reader can skip to the segment containing a sought item instead of
decoding from byte zero, and an update re-encodes one segment (`README:269-275`).
One proven invariant: **removing an item from a delta-varint list never increases
its encoded size** (`ginpostinglist.c:55-71`) — which is why deletes can be
absorbed in place (vacuum) while inserts must be buffered (pending list).

**The fastupdate pending list — the field's closest analog to vfs's scan
overlay.** Inserts append (key, TID) tuples to an unsorted chain of pages off the
metapage — no sorting, no tree descent (`ginfast.c:218-545`). Every search scans
the **entire** pending list before touching the main tree, and the order is
load-bearing: overlay first, or a concurrent cleanup can make the scan miss
entries; duplicate visits are harmless because results are a bitmap
(`ginget.c:1950-1960`). Cost is linear in pending rows, with the full consistency
check run per row (`ginget.c:1836-1925`). Cleanup: triggered by a size backstop
(`gin_pending_list_limit`, default 4 MB — fired deliberately *below* the cap so
one pass suffices, `ginfast.c:448-471`), by (auto)vacuum, and by a manual
function; a rival cleaner causes an ordinary insert's attempt to just bail
(`ConditionalLockPage`, `:807-828`); the drain snapshots the tail at start so
sustained writes can't make it endless (`:843-847`); and it merges into the tree
*before* unlinking pending pages, so a crash costs a redundant re-post, never a
loss (`:767-772`). The planner reads `nPendingPages` live off the metapage —
the one always-fresh statistic — and charges the whole pending list as **startup
cost** before any selective work (`selfuncs.c:8682-8696, 8851-8855`). The docs
name the failure mode plainly: "a large list of pending entries will slow
searches significantly," prefer background cleanup, and turn fastupdate off when
consistent response time beats write speed (`gin.sgml:525-541, 599-621`). For
bulk loads: drop and recreate the index — past some batch size wholesale rebuild
beats incremental merge (`gin.sgml:570-586`), which is vfs's existing posture.

**pg_trgm.** Extraction: alnum words padded 2 blanks left / 1 right, compile-time
case folding, trigrams are exactly 3 bytes with multibyte trigrams *CRC-hashed*
into 3 bytes — deliberately lossy, licensed by recheck (`trgm.h:16-25`,
`trgm_op.c:373-393`). The gram set is a sorted dedup'd set — no positions, no
counts (`trgm_op.c:598-620`). LIKE compiles to an AND-set from literal fragments
(`trgm_op.c:1000-1154`); regexes go through an NFA → color-trigram graph
transformation whose evaluation is graph reachability over "which trigrams are
present," with lossy state-merging under hard limits and a whitespace-penalty
heuristic for which trigrams to drop (`trgm_regexp.c:1-190, 211-240`); no
extractable trigrams degrades to a full scan (`GIN_SEARCH_MODE_ALL`,
`trgm_gin.c:134-138`). And recheck is **unconditional for every strategy**
(`trgm_gin.c:187-188`): GIN never trusts the index for these operators — the
executor refetches the heap tuple and re-evaluates the original predicate
(`nodeBitmapHeapscan.c:196-210`). Same one-sided contract as vfs: false positives
allowed, false negatives never; lossiness anywhere is fine so long as it
over-approximates.

### Maps to vfs how

- **Direct (overlay discipline — the pending list's rules, restated for vfs):**
  (1) overlay-scan-first ordering with set-union semantics as a *stated
  invariant*; (2) the merge/rebuild snapshots its input set up front and drains
  only that; (3) publish-then-demote ordering (new epoch visible before overlay
  watermark advances) with an idempotent, re-runnable merge — vfs's epoch CAS +
  flag flips already have this shape, GIN confirms the ordering is the
  load-bearing part; (4) **two triggers, not one**: a background cadence plus a
  size backstop that fires below the cap and *bails if a rival holds the lease*;
  (5) express the overlay cap in **documents, not bytes** (the scan cost is
  linear in docs) and derive it from a target added latency; (6) planner reads
  the overlay's live size and charges it as fixed startup cost — past a
  threshold, "scan everything" beats "index + overlay" and the plan should say
  so. Also: GIN binary-searches each pending row's pre-extracted sorted entries
  rather than re-deriving them (`ginget.c:1662-1699`) — the analogous vfs option
  is storing each overlay doc's sorted gram set at write time so overlay probes
  are merges, not re-extractions.
- **Adaptable**: segmented posting blobs — length-prefixed segments each
  restarting at an absolute doc id, enabling skip-ahead intersection and early
  termination without decoding from byte zero (GIN's 256 B target is a page
  artifact; vfs's segment size should be set by decode cost). The
  deletion-never-grows invariant opens a cheap maintenance move vfs doesn't
  currently have: in-place tombstoning of deleted docs between epochs (deletes
  shrink blobs; only inserts force the overlay). Stable gram keyspace across
  rebuilds — UPDATE payloads rather than DELETE+INSERT rows — since gram
  vocabulary is near-stationary (GIN's no-key-delete rationale).
- **Dead on arrival**: posting trees (they exist for 8 KB page granularity,
  concurrent in-place insertion, and vacuum-under-concurrency — none of which
  vfs's wholesale rebuild has; the SQL-row analogue of "too big for one tuple"
  is flat row chunking, not a tree); pg_trgm's CRC-hashed 3-byte trigram
  compaction (vfs's gram space doesn't need fixed-width hashing).

---

## 5. livegrep — suffix arrays (public design writing; no checkout)

### Findings

Livegrep concatenates the (line-deduplicated) corpus into one buffer and builds a
suffix array over it with libdivsufsort — no inverted index; every substring is
indexed (Nelhage, "Regular Expression Search with Suffix Arrays",
blog.nelhage.com/2015/02/...). A regex becomes nested character-range narrowings:
find the SA range for the first character class, subdivide within it for the
next, recursively — each step a binary search; resulting positions are sorted,
coalesced into ranges, and RE2 verifies each range. Documented footprint: "the
index file... will usually be 3-5x the size of the indexed text," mmap'd, with
explicit advice that it should fit in RAM (livegrep README). The access pattern
is the killer: every binary-search probe dereferences `SA[mid]` *into the corpus*
at an arbitrary offset — two random accesses per probe, ~30 probes per boundary
on a 2^30-byte corpus, many boundaries per regex, unbatchable. Cursor's recent
writeup independently makes the same point and adds that a suffix array is
monolithic and non-incrementally-updatable (cursor.com/blog/fast-regex-search).

### Maps to vfs how

**Dead on arrival for SQL rows**, twice over: (1) probe amplification — one row
round trip per binary-search probe against random corpus offsets cannot be
batched into range scans; (2) epoch mismatch — a single global sorted permutation
over concatenated content re-permutes arbitrarily on any change, so an epoch
rebuild rewrites 4–8 bytes per corpus byte with no natural row-granular unit.
Viable only RAM-resident, which is the design vfs is deliberately not. Its one
transferable idea — coalescing nearby candidate positions into ranges and
verifying once per range — reappears in the positional-postings organization
(§1, §8) where it *is* SQL-compatible.

## 6. Roaring bitmaps — posting encoding (public papers/docs)

### Findings

Structure: the 32-bit id space is split into 2^16-value chunks; each chunk is an
array container (≤4096 sorted uint16s), a bitmap container (8 KB fixed), or a run
container — the 4096 threshold guarantees ≤16 bits/value (Chambi et al.,
arXiv:1402.6407 §2; run containers: Lemire et al., arXiv:1603.06549).
Intersections operate per container without full decode: word-wise AND + popcnt,
bit probes for array×bitmap, and **galloping** merge when array cardinalities
differ >64× (1402.6407 §4). Measured speedups are ×4–5 to "up to 900×" — but
**versus RLE bitmap formats (WAH/Concise), not versus sorted varint deltas**; no
published Roaring-vs-delta-varint intersection benchmark exists, and the papers'
own density floor ("less than 0.1% ... a bitmap is unlikely to be the proper data
structure") marks the sparse regime where delta-varint (~8 bits/doc dense-ish) is
as good or better than Roaring's 16-bit floor. Adoption is broad — Lucene
(`RoaringDocIdSet` for cached filters <1% density), Druid, ClickHouse, Pinot — and
**pg_roaringbitmap** ships a real Postgres `roaringbitmap` column type with
AND/OR operators and aggregates in the portable CRoaring format
(github.com/ChenHuajun/pg_roaringbitmap). The portable serialization
(RoaringFormatSpec) is a self-describing byte string with a per-container
**offset header enabling random access without full materialization** —
cross-language (C/Java/Go), plus CRoaring's mmap-able frozen format.

### Maps to vfs how

**Adaptable — selectively, keyed on density, and honestly ranked as a
third-order win.** The portable format drops into a BLOB/BYTEA/VARBINARY column
unchanged and its offset header beats vfs's decode-from-byte-0 blobs for
skip-ahead; on Postgres specifically, pg_roaringbitmap could push the gram
intersection server-side so only the surviving doc set crosses the wire. But
vfs's rare-gram tail sits below Roaring's density floor, where the current codec
is equal or smaller — the defensible shape is a per-blob encoding tag (roaring
for dense grams, delta-varint for the tail), which is extra machinery. Against
the measured cost order, posting decode+intersect is *third*; Roaring attacks
neither fetch bytes nor assembly. Note also that GIN-style segmenting of the
existing codec (§4) buys the same skip-ahead property with less novelty.

## 7. Result/query caching — Lucene/Elasticsearch (public docs)

### Findings

Two caches, two keys. Lucene's `LRUQueryCache` caches filter results **as docid
bitsets per segment** (RoaringDocIdSet under 1% density), only for segments
holding ≥10k docs and ≥3% of the shard (Lucene javadoc; elastic
node-query-cache-settings). Elasticsearch's shard request cache stores whole
per-shard result objects keyed by a hash of the request body, "invalidated
automatically whenever the shard refreshes" (elastic shard-request-cache doc).
The underlying philosophy: segments are immutable, so a (query, segment) entry
can never go stale — it is never invalidated, it just dies when its segment is
merged away (elastic "Frame of Reference and Roaring Bitmaps"; "Dynamic
Indices"). The coarse cache (whole results) invalidates on every refresh; the
fine cache (per-segment bitsets) survives refresh indefinitely. Operational
details worth keeping: budget caches in bytes, not entries; and Lucene's
don't-bother heuristic — skip caching where re-execution is cheaper than the
cache overhead.

### Maps to vfs how

**Direct — vfs's epoch id is a strictly better cache key than Lucene's segment
id** (whole-corpus immutability, one bulk drop at epoch reclaim instead of
per-merge bookkeeping). Within an epoch, gram→postings and doc→content are both
frozen, so every derived value is valid for the epoch's lifetime with zero
invalidation logic. Field-suggested granularities, all keyed `(epoch, …)`:
`(epoch, gram) → posting blob` (highest reuse — the analogue of the filter
cache); `(epoch, canonical query) → candidate doc set`; `(epoch, canonical
query) → result` (mind ES's sharp edge: canonicalize before hashing); and — the
one that attacks vfs's *dominant* cost directly — `(epoch, doc) → content`, a
byte-budgeted LRU. Lucene gets the content cache for free from the OS page cache
over immutable segment files; a SQL-backed store has to build it explicitly, and
the epoch protocol is precisely what makes it safe. One epoch subtlety vfs
already handles: the scan-overlay (`NOT encoded`) side is *not* epoch-frozen, so
only index-tier results are cacheable — which vfs's flag partition makes
cleanly separable.

## 8. Sub-document verification and chunked content (mixed source + public docs)

### Findings

Chunk-level candidate granularity is a mainstream, shipped design point, arrived
at from two directions.

*Search side.* Zoekt's postings are already sub-document positions (§1). FTS5's
`detail=` ladder is a document-region granularity dial, though its positions are
token ordinals, not byte offsets, so they can't drive a fetch range without a
forward map (§3). Lucene treats "where in the document" as a stored artifact —
offsets in postings or term vectors — explicitly to avoid re-reading/re-analyzing
whole fields, naming the same trade vfs faces ("may result in a significantly
larger index"; UnifiedHighlighter docs). Lucene's stored-fields format is the
closest structural analogue to a chunks table: bodies compressed in ~16 KB blocks
with per-block length metadata so the reader "can stop decoding as soon as enough
data has been decompressed" (Lucene50StoredFieldsFormat docs). Block-max WAND
generalizes the shape — cheap per-block summaries between posting list and
payload let queries skip blocks untouched, 3–7× on term queries (Grand et al.,
ECIR 2020). And Elasticsearch's `semantic_text` ships chunk postings outright:
long fields split into ~250-word chunks with **100-word overlap**, each chunk
indexed and addressed as "start and end character offsets... pointing to the
exact location of each chunk within the original input text" (elastic
semantic_text reference). BitFunnel is the instructive negative: doc-granularity
signatures, no positions, full-doc downstream verification — the design point
closest to vfs today, and its length-sharding is an admission that doc-size
heterogeneity is what wrecks doc-granularity filtering (SIGIR 2017).

*Storage side.* The dedup world keys chunks by content: borg cuts with buzhash
(min 512 KiB / target 2 MiB / max 8 MiB) but dedups on a separate strong hash —
"buzhash is only used for cutting" (borg data-structures docs); restic is Rabin
CDC, blobs 512 KiB–8 MiB, SHA-256 identity (restic design.rst). The filesystem
world does the opposite — **both studied checkouts are offset-based, neither
content-defined**: juicefs uses fixed 64 MiB chunks / write-slices / 4 MiB
blocks, positionally keyed, reading only the blocks overlapping a byte range
(juicefs `docs/en/introduction/architecture.md:36-67`,
`pkg/chunk/cached_store.go:40`), and explicitly rejects dedup as too expensive at
scale (`juicefs_vs_s3ql.md:21`); seaweedfs chunks arithmetically at 4 MB with
chunk identity = physical needle address (`weed/pb/filer.proto:183-197`,
`weed/command/filer_copy.go:456-467`), collapses >10,000-chunk lists into
manifest chunks (`weed/filer/filechunk_manifest.go:23`), and its read path is
exactly the needed operation — resolve the chunks overlapping `[offset, stop)`
and clip each to the request (`weed/filer/filechunks.go:188-215`).

*Synthesis facts.* Positional retrieval always keys by entity+position, never
content hash (content-hash keying serves dedup and *costs* the offset→chunk
arithmetic). CDC's stability property is unused if the whole entry re-chunks on
write. The dedup size envelope (512 KiB floor) is wrong for grep verification —
most source files are smaller than one borg minimum chunk, which would degenerate
chunk fetch to whole-file fetch; retrieval-side precedents sit at 16 KB (Lucene)
to 4 MB (seaweedfs/juicefs). The boundary-straddle problem has three shipped
answers: index-time overlap (ES's 100-word overlap; 2 bytes suffices for trigram
attribution), fetch-time neighbor expansion (seaweedfs's clip pattern; expand
candidate pos ± max-match-length), and — the load-bearing correctness rule — the
straddle fix **must land at index time for the postings**: a boundary-straddling
trigram dropped at index time is a false negative no fetch-time expansion can
recover, because a chunk containing none of the pattern's indexed trigrams is
never fetched. (vfs's own extraction invariant — "every trigram of the entry's
folded body is in the entry's posted gram set", `indexing.py:16-21` — already
states exactly this rule at entry grain; chunk-grain postings would need to
preserve it across boundaries.)

### Maps to vfs how

**Adaptable, leaning direct — this is the organization that attacks the measured
bottleneck head-on.** vfs already has the two halves lying separate: a chunks
table with `(entry_id, chunk_index)` identity and `line_start`/`line_end`
(`src/vfs/models/chunk.py:33-48`) that the gram path deliberately ignores, and a
content table fetched whole. The field's translation: give postings sub-document
locality (chunk ordinal at minimum, byte offset at maximum), key verification
chunks by entry+ordinal with offset/line columns, fetch only chunks overlapping
candidate regions (the seaweedfs clip), expand by pattern length at fetch time,
and guarantee straddle coverage at index time. Note the semantic chunks table as
it stands is the wrong fetch unit (tree-sitter boundaries, variable sizes, built
for embedding); a verification fetch unit wants fixed arithmetic boundaries. Do
not import CDC or backup-world chunk sizes. Payoff concentrates in the body-size
tail — worth measuring vfs's distribution, though the linux-tree profile (200 MB
fetched for 2.5k matching lines) already shows the tail is where the money is.

---

## Ranked shortlist: what most directly attacks "fetch bytes dominate" and "verify scans whole bodies" under SQL-row storage

**1. Sub-document posting locality + range-clipped verification fetch**
(zoekt §1 + FTS5's detail ladder §3 + ES semantic_text and the seaweedfs clip
§8). The only organization in the study that eliminates the dominant cost rather
than amortizing it: postings carry where-in-the-doc (chunk ordinal or byte
offset), verification fetches only the covering chunk rows, and Cox's own
sentence names the prize — never load a document that isn't (nearly) guaranteed
to match. The price is indexed bytes, and the field brackets it precisely:
exact offsets ≈ 5.5× rowid-only (FTS5) / ~2x corpus (zoekt); a coarse chunk-tier
≈ 2.5× (FTS5 detail=col) — and it buys the *further* option of zoekt's
distance-merge, which reads only two posting blobs per atom while emitting exact
candidate offsets. Hard constraints from the field: straddle coverage at index
time (false-negative hazard), fixed arithmetic chunk boundaries keyed
entry+ordinal, retrieval-scale chunk sizes (tens of KB, not backup-scale MB),
byte offsets not rune offsets, and zoekt-style bloat gates (per-doc trigram cap,
size cap) before positions multiply pathological files.

**2. Epoch-keyed caching, especially `(epoch, doc/chunk) → content`** (§7).
Zero index-format change, small implementation, and the only lever that helps
*repeated* heavy queries immediately: the epoch protocol already provides
perfect immutability keys at whole-corpus granularity — better than the segment
keys Lucene builds its entire caching stack on. A byte-budgeted content LRU is
the direct analogue of the OS page cache that makes zoekt/codesearch's
whole-body reads survivable, i.e. it is the missing piece vfs lost by moving
bodies behind SQL. `(epoch, gram) → postings` and `(epoch, query) → candidates`
ride along nearly free. Complements #1; replaces nothing.

**3. Per-doc/per-chunk auxiliary metadata that answers questions without
content** (zoekt's newline blobs §1; FTS5's dlidx-as-columns §3; block-max-style
per-chunk gram summaries §8). Attacks the second cost (result assembly) and
tightens #1: a per-doc newline index gives line numbers and line byte-ranges
with zero content bytes; `first_doc`/`last_doc` columns on posting chunk rows
let SQL skip blob shipment entirely; a per-chunk gram bloom rejects chunks
pre-fetch. Individually small, additive, and each is a plain SQL column or tiny
blob row — the most SQL-native ideas in the study.

**4. Segmented posting blobs + GIN's overlay discipline** (§4, FTS5 §3).
Third-order against fetch bytes but cheap and proven: length-prefixed posting
segments with absolute restarts give skip-ahead intersection and early
termination inside vfs's existing codec (subsuming most of Roaring's practical
benefit without a format gamble); and GIN's pending-list rules — dual triggers
with a below-cap size backstop, cap denominated in documents, live overlay size
gating plan choice, publish-before-demote idempotence — harden the scan overlay
vfs already ships against exactly the degradation GIN documents.

Explicitly ruled out for SQL rows: suffix arrays (probe amplification + epoch
mismatch, §5); FTS5's LSM merge apparatus for posting data (§3); GIN posting
trees (§4); mmap-shaped "load the doc" call shapes anywhere above the storage
seam (§1, §2). Roaring remains a measured-bet option for dense grams only, and
only after #4's segmenting, which it partially duplicates (§6).
