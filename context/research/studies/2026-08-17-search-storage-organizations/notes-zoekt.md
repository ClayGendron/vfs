# zoekt (raw agent findings)

Checkout: ~/Git/Repos/zoekt (Apache-2.0). Format version 6.

## 1. Format: postings are POSITIONS (corpus-global rune offsets), delta+varint
- shard_builder.go:184-248 — per rune position, running trigram's offset appended. shard_builder.go:214 `newOff := endRune + uint32(runeIndex) - 2` (endRune = corpus-global rune count at doc start → offsets global, monotone across docs).
- shard_builder.go:238-247 — `delta := newOff - pl.lastOff`, varint into per-ngram byte slice (postingList.data, :66-69); single-byte fast path, comment "~80% of deltas are < 128".
- ASCII trigrams: direct-indexed [1<<21]*postingList array; non-ASCII: map (shard_builder.go:89-93, 216-237). ngramSize=3 (shard_builder.go:39).
- No count prefix (v6 removed it — toc.go:20); blob = pure deltas, first varint absolute (hititer.go:188-196).

## Section structure
- toc.go:71-104 TOC; simpleSection = (off,sz) (section.go:101-134); compoundSection = data + per-item uint32 start offsets (section.go:136-170); relativeIndex() → boundaries arrays (section.go:198-207; read.go:287-292, 343). lazyCompoundSection (section.go:209-224).
- TOC written last, file ends with 8-byte pointer to it (write.go:239-245; read.go:182-201). Sections tagged/self-describing → forward compatible (write.go:40-51; read.go:110-159).
- writePostings (write.go:81-125) emits ngram-sorted: 1) ngramText (8 B big-endian per ngram; three 21-bit runes in uint64 — bits.go:82-84; read.go:472), 2) postings compound section, 3) runeOffsets, 4) fileEndRunes.

## Ngram lookup: B+-tree, mmap'd leaves
- btree.go:1-29 doc; bucket = one page: btreeBucketSize=(4096*2)/8=1024 ngrams (btree.go:47). Leaves store no ngrams — only bucketIndex + postingIndexOffset (btree.go:153-169, 399-410).
- Get (btree.go:314-352): in-memory descent → 1 bucket read → binary search → getPostingList reads 8 bytes (two uint32 offsets) → simpleSection{off,sz} (btree.go:359-397). Tree rebuilt at load by re-inserting ngrams (read.go:474-499).
- Posting section `sz` used as trigram FREQUENCY without reading blob (indexdata.go:437, 442).

## 2. Position use at search time
- iterateNgrams (indexdata.go:416-500): splitNGrams gives every pattern trigram + its rune index in pattern (bits.go:126-157); lookups sorted so adjacent ones hit same btree bucket (indexdata.go:427-429); zero-frequency trigram → noMatchTree short-circuit (indexdata.go:446-455).
- findSelectiveNgrams picks the TWO lowest-frequency trigrams, shifted apart if overlapping (indexdata.go:337-383).
- Distance merge: newDistanceTrigramIter(first, last, runeDist=last.index-first.index) (indexdata.go:474-481); distanceHitIterator.findNext (hititer.go:51-69) advances until p1+distance == p2. Candidate = corpus offset where both trigrams sit at the pattern's internal distance — not a document. Skip-ahead next(limit) = forward scan over varint blob (hititer.go:206-223).
- Offset→doc: ngramDocIterator (matchiter.go:117-210) with ends=fileEndRunes (indexdata.go:468-472); nextFileIndex = GALLOPING search over fileEndRunes (matchiter.go:132-147); candidates() emits exact in-doc runeOffset = p1 - fileStart - leftPad; leftPad/rightPad reject boundary-straddling hits (matchiter.go:180-210, 199-201; indexdata.go:463-467). prepare(nextDoc) seeks posting iter to doc start (matchiter.go:161-170).
- Verification at offset: substrMatchTree.matches (matchtree.go:958-989) → findOffset + matchContent; matchContent (matchiter.go:50-68) = bytes.Equal at [byteOffset : byteOffset+len] — NO scan, no regex for substring atoms; O(pattern len)/candidate.
- CAVEAT: cp.data(false) returns whole doc as zero-copy mmap slice (contentprovider.go:81-92; read.go:524-529; indexfile.go:34-39) — only pages containing the offset fault in; ContentBytesLoaded stat overstates I/O (contentprovider.go:89). Only genuine byte-range read: readContentSlice(byteOff, 300) for findOffset (read.go:531-538; contentprovider.go:123).
- Regex atoms still scan whole docs: regexpMatchTree.matches FindAllIndex over cp.data (matchtree.go:810-845); positions gate WHICH docs via andMatchTree + noVisitMatchTree (matchtree.go:1002-1031).
- Cost ladder: costConst=0 < costMemory=1 < costContent=2 < costRegexp=3 (matchtree.go:51-61); per-doc loop evaluates at increasing cost, bailing on matchesNone (eval.go:276-289). Substr verify at costContent (matchtree.go:971-973); regex at costRegexp (matchtree.go:815-817).
- andLineMatchTree (matchtree.go:681-765): for single-line multi-literal regexes (singleLine tracked in regexpToMatchTreeRecursive, eval.go:610-676): fewest-candidate child's offsets → lines via cp.newlines().atOffset; merge-join others' offsets against line ranges; reject doc WITHOUT running regex if no single line holds all terms. "Positions replace scanning" in purest form.

## 3. Size overhead (documented)
- design.md:66-70: index ≈ 3x corpus = 2x offsets + 1x original content. design.md:145-146: shard ≈ 3.5x corpus. faq.md:112-114: SSD for 3.5x index; RAM ≥ corpus+20%. design.md:79-81: positional trigrams need only ~1.2x corpus RAM because posting lists can live on SSD (only two lists read per atom — design.md:56-64).
- Positional posting data ≈ 2x corpus ≈ 57% of shard.
- Caps: uint32 offsets → shard <4GB, content ≤1GB/shard (design.md:148-150). ShardMax=100<<20, SizeMax=2<<20 (2MB/file), TrigramMax=20000 distinct trigrams/doc (builder.go:325-333); DocChecker skips binary (shard_builder.go:680-720).
- Resident memory: only btree inner nodes, boundary arrays, rune-offset maps (indexdata.go:313-335 memoryUse); postings + leaves not resident.

## 4. Case-insensitivity: query-side expansion, no folded copies stored
- design.md:92-98. generateCaseNgrams walks unicode.SimpleFold over 3 runes, ≤8 variants (bits.go:26-47). Frequency = sum over variants (indexdata.go:440-443). trigramHitIterator reads one blob per variant, unions via mergingIterator (hititer.go:115-146, 232-267).
- Verify case-foldingly at the offset only: caseFoldingEqualsRunes(substrLowered, content[off:]) (matchiter.go:56-67; bits.go:62-78); returns byte size (fold can change byte length); substrLowered via toLower once per atom (bits.go:49-57; indexdata.go:490-498). Regex atoms: `(?i)` prefix (matchtree.go:210-216). Cost: ≤8× lookups/trigram (NgramLookups stat, api.go:418-419), 0× storage.

## 5. Line-number resolution (no content reads needed)
- newlines compound section: per doc, delta-varint list of BYTE offsets of every \n (write.go:137-141, 259-267); read per-doc on demand, cached on contentProvider (contentprovider.go:71-79; read.go:540-558). Offset→line = sort.Search (contentprovider.go:472-477); line→byte offset = locs[n-2]+1 (:482-493); line text = data[lineStart(low):lineStart(high)] (:508-514). Blob's leading varint doubles as newline count (indexdata.go:283-299).
- fileEndRunes (rune space, for postings) + boundaries (byte space, free from fileContents compound index) (read.go:287-288, 377; write.go:122-124). setDocument O(1) file size (contentprovider.go:50-59).
- runeOffsets: rune→byte sampled every 100 runes (shard_builder.go:60, 199-201), stored as correction list where 1-byte-per-rune breaks (runeOffsetMap, bits.go:342-402); findOffset binary-search + ≤100-rune walk over a 300-byte slice (contentprovider.go:97-137); PlainASCII flag short-circuits to identity (write.go:218; contentprovider.go:98-100). columnHelper incremental per line (contentprovider.go:430-458).

## 6. Content in the index file, uncompressed, mmap'd
- write.go:136 writeStrings raw; section.go:162-165. No gzip/zstd/snappy anywhere in index/. Whole-shard mmap (indexfile.go:57-81); every read = f.data[off:off+sz] slice (indexfile.go:34-39); slices alias mmap (read.go:581-584; contentprovider.go:145-146).

## Draft verdict (agent's)
DIRECT: (1) positional delta+varint postings — same blob shape vfs has, values become offsets; (2) two-trigram distance intersection — highest leverage: exact candidate start offsets from only TWO posting blobs per atom (read volume goes DOWN); (3) posting length column as selectivity signal (pick rarest grams without fetching blobs); (4) case-insensitivity by query expansion (≤8× lookups, 0 storage); (5) per-doc newline index as small delta-varint blob (line numbers + line byte ranges with zero content bytes); (6) doc-boundary array + galloping offset→doc; (7) cost ladder — content-touching predicates strictly last.
ADAPTABLE: (8) verify against byte RANGE not document — port readContentSlice's shape: candidate offsets → covering chunk rows [floor((off-k)/chunk), ceil((off+len+k)/chunk)]; needs (doc_id, chunk_ord) fixed-size chunks so offset→row is arithmetic. "This is where the 200MB goes to ~a few MB... the whole ballgame." (9) offset namespace: corpus-global per epoch (renumber each rebuild) vs (doc_id, in-doc offset) doc-major delta encoding — (b) right for epoch-versioned SQL rows, also removes doc-boundary array. (10) regex windows: zoekt doesn't solve (whole-doc FindAllIndex); transferable = andLineMatchTree + singleLine classification → fetch and regex only candidate lines for single-line regexes; multi-line falls back to full doc, classify at plan time. (11) store BYTE offsets not rune offsets — rune apparatus is a Unicode-fold tax (300-byte read per candidate just to convert); byte-oriented Rust regex doesn't need it.
DOA: (12) mmap/"content lives in index" — "load the doc, read 20 bytes" is correct only under demand paging; copying that shape over a DB link IS the 200MB symptom. (13) the ngram B+-tree — SQL PK index already is this; salvage: sorted batched IN(...) lookups (bucket-locality analogue). (14) uint32/4GB shard caps. (15) 3.5x size ratio as target — vfs's marginal cost is ~2x-corpus offsets in posting rows; needs zoekt's mitigations (TrigramMax 20000/doc, binary skip, 2MB file cap) or minified/generated files dominate the table.
