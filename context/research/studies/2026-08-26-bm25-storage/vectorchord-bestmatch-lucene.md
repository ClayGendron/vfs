# Study: VectorChord-bm25, pg_bestmatch.rs, and Lucene's postings — how three BM25 indexes store postings, statistics, and block-max bounds

- **Study for**: [2026-08-26-bm25-storage-design.md](../../2026-08-26-bm25-storage-design.md)
  §2 (prior art) and §5 (the opinion) — what a `(epoch, term, block)`
  row must carry, which block size, whether to quantize norms, and
  which ideas survive without an index access method.
- **Date**: 2026-08-26
- **Sources** (reference checkouts read-only, refreshed to their
  upstream default branches 2026-08-26, cited as `path:line`; nothing
  copied):
  - `~/Git/Repos/VectorChord-bm25` @ 14fc2a3 (`main`, 2026-04-28,
    AGPL-3.0 / ELv2 dual) — a single squashed commit, so no history
    to trace.
  - `~/Git/Repos/pg_bestmatch.rs` @ 0a3b574 (`main`, 2024-11-05,
    Apache-2.0).
  - `~/Git/Repos/lucene` @ 0cc09c8 (`main`, 2026-08-26, Apache-2.0);
    paths below are relative to
    `lucene/core/src/java/org/apache/lucene/`.
- **In-tree context**: spec 130 (landing note: 3.09 M term rows for
  32 k chunks, 3.7 KB per chunk, 2.02× content), the MSSQL spike
  (`2026-08-26-bm25-vs-mssql-fulltext.md`: 111 MB `lex_terms` vs a
  23.5 MB native catalog), and the gram index's shape
  (`models/postings.py`, `storage/backends/database/indexing.py`,
  `grep.py`).

---

## A. VectorChord-bm25 — a Block-WAND index as a Postgres access method

### A.1 What the index type is, at this commit

The README describes a `bm25vector` type produced by a separate
`pg_tokenizer.rs` extension (README.md:11, 41-46). The code at
14fc2a3 is one release ahead of it: the operator class is declared
**for `tsvector`** (`src/sql/finalize.sql:34-35`), the query type is
`bm25query AS (vector tsvector, index regclass)` (:3-6), and the
operator `<&>` takes `tsvector` on the left (:10-14). Tokenization is
therefore whatever produced the tsvector — `to_tsvector('english', …)`
in every test (`tests/sqllogictest/bm25query.slt:24`) — and the term
frequency is the tsvector's *position count*
(`src/datatype/tsvector.rs:84-94`, `count.expect("tsvector must have
positions")` at :88). The 0.3.0 install script still carries
`bm25vector` (`sql/install/vchord_bm25--0.3.0.sql:135-189`); the
README's tokenizer section describes that older surface.

**Terms have no vocabulary table.** A lexeme becomes a fixed 16-byte
key (`crates/bm25/src/lib.rs:37`, `WIDTH = 16`): lexemes shorter than
16 bytes are stored verbatim, longer ones are replaced by the first 16
bytes of a *keyed* blake3 hash, the key being a per-index random seed
kept in the meta page (`crates/bm25/src/vector.rs:19-35`;
`src/index/bm25/am/am_build.rs:143` draws the seed,
`crates/bm25/src/tuples.rs:50-57` stores it). Term identity is
content-addressed; a query interns its lexemes the same way and looks
them up in a static multi-level index (`address_tokens.rs`).

### A.2 Storage: one sealed segment plus a growing tape, all in 8 KB pages

Everything lives in ordinary Postgres index pages (`PostgresPage` is
exactly `BLCKSZ`, `src/index/storage.rs:26-46`), organised as
singly-linked "tapes" of pages (`crates/bm25/src/tape.rs`). A built
index has (`crates/bm25/src/flush.rs:40-158`, `build.rs:22-71`):

| tape | tuple | content |
|---|---|---|
| meta (page 0) | `MetaTuple` | `k1`, `b`, seed, pointer to the jump tuple (`tuples.rs:50-57`) |
| jump | `JumpTuple` | **`number_of_documents`, `sum_of_document_lengths`** (N and Σdl), pointers to every other tape (`tuples.rs:143-160`) |
| documents | `DocumentTuple` | `deleted`, **`fieldnorm: u8`** (quantized dl), `payload` = ctid as `[u16;3]` (`tuples.rs:758-762`) |
| tokens | `TokenTuple` | 16-byte key, **`number_of_documents` (df)**, `wand_fieldnorm`, `wand_term_frequency`, pointer to its first summary (`tuples.rs:835-843`) |
| summaries | `SummaryTuple` | per block: `min_document_id`, `max_document_id`, `number_of_documents: u8`, `wand_fieldnorm: u8`, `wand_term_frequency: u32`, pointer to the block (`tuples.rs:902-911`) |
| blocks | `BlockTuple` | compressed doc ids + compressed tfs, one metadata byte each (`tuples.rs:975-983`) |
| vectors | `VectorTuple` | the **growing segment**: raw sparse vectors appended by `aminsert` (`insert.rs:23-79`) |

**Block = 128 postings** (`flush.rs:82`). Doc ids inside a block are
d-gap coded from the block's `min_document_id` and bit-packed with one
fixed width per block when the block is full (`compression.rs:36-63`;
the width is the OR of the gaps, `simd/src/bitpacking_u32_ordered.rs:17-27`);
a tail block shorter than 128 is byte-packed (1–4 bytes per value,
flag bit in the metadata byte). Term frequencies are bit-packed without
delta coding (`compression.rs:94-110`). No patching/exceptions, no
positions — the format is docs-and-freqs only. A full block of a
mid-frequency term costs roughly (gap bits + tf bits) × 128 / 8 + 16-byte
header + a 24-byte summary: on the order of **1–2 bytes per posting**.

There is **one sealed segment**, not several. `aminsert` appends the
raw document vector (plus a `fieldnorm` marker tuple) to the vectors
tape (`insert.rs:57-78`) and touches no statistics. Search brute-forces
the *entire* vectors tape on every query (`search.rs:83-135`) before
running Block-WAND over the sealed segment. Sealing happens in
`maintain` (`crates/bm25/src/maintain.rs:27-311`), called from
`amvacuumcleanup` — i.e. **on VACUUM** (`am_vacuumcleanup.rs:39`): it
re-reads every sealed document and block, drops deleted documents and
relabels ids (`maintain.rs:330-362`), appends the growing vectors,
external-sorts the whole mapping set again, `flush`es a brand-new
segment (`maintain.rs:266`), swaps the jump tuple's pointers and frees
the old pages (`maintain.rs:282-308`). That is a whole rebuild of one
segment — structurally the same discipline as vfs's epoch rebuild.

The README's `bm25_catalog.segment_growing_max_page_size` GUC
(README.md:466) **does not exist in this code**: the only GUCs are
`bm25.enable_scan`, `bm25.limit`, `bm25.prefilter`
(`src/index/gucs.rs:29-54`). The README's "sealed into a read-only
segment when the growing segment exceeds N pages" is either older or
planned; at 14fc2a3 the trigger is VACUUM and there is no size cap.

### A.3 Where df, N and avg_dl live, and how current they are

- `N` and `Σdl` sit in the jump tuple; `avgdl = Σdl / N` is recomputed
  at query start (`search.rs:49-51`, `evaluate.rs:40-42`). `Σdl` is
  exact (u64 of exact lengths, `flush.rs:54-58`) even though each
  document's own length is stored quantized.
- `df` per term is in the token tuple (`flush.rs:130`), summed over
  blocks at flush.
- **None of these change on insert or delete.** `bulkdelete` only sets
  `deleted` flags (`bulkdelete.rs:23-111`); insert appends to the
  vectors tape. Until VACUUM re-flushes, idf and avgdl are the sealed
  segment's. Worse: the query's token list is built from the sealed
  token tuples only (`search.rs:53-79`), and the growing-tape scan
  scores an element only if its key is in that list
  (`search.rs:100, 114`) — **a term that first appears in an inserted
  document contributes nothing until the next VACUUM.** The statistics
  are "kept current" exactly as often as the segment is rebuilt.

### A.4 The formula and the 256-entry caches

- `idf = ln((N + 1) / (df + 0.5))` (`bm25.rs:285-289`) — tantivy's
  form, **not** Lucene's `ln(1 + (N − df + 0.5)/(df + 0.5))`; it differs
  by the numerator's `−df`, small for rare terms, larger for common ones.
- `tf-factor = tf(k1+1) / (tf + k1(1 − b + b·dl/avgdl))` (`bm25.rs:291-295`)
  — keeps the `(k1+1)` numerator, as vfs does.
- `dl` is decoded from a one-byte `fieldnorm` through a 256-entry table
  (`bm25.rs:15-283`); the table is exactly Lucene's `byte4` decoding
  (see C.4): 0–39 exact, then 4 significant bits up to 2,013,265,944.
- Per query term a `Cache` holds `s0 = idf·(k1+1)` and
  `s1[256] = k1(1 − b + b·dl(fieldnorm)/avgdl)`; a posting scores as
  `tf·s0 / (tf + s1[fieldnorm])` (`bm25.rs:334-359`) — one multiply, one
  add, one divide, one table lookup, the same shape as Lucene's scorer.
- `k1` is validated to `[1.2, 2.0]` and `b` to `[0, 1]`
  (`types.rs:20-27`); the score is negated for `ORDER BY … ASC`
  (`operators.rs:54`).

### A.5 Block-WeakAnd: the per-block metadata and the loop

Build time: for every block the flusher runs each `(fieldnorm, tf)`
pair through the real tf-factor with the corpus `avgdl` and keeps the
**single pair that maximises it** (`Wand::push`, `bm25.rs:311-318`;
`flush.rs:101-110`); the term's own pair is the max over its blocks
(`flush.rs:112`). So a summary carries one `(wand_fieldnorm,
wand_term_frequency)` — the argmax pair that actually occurs in the
block — and the token tuple carries the term-level one. The bound is
tight (it is an observed pair) and valid because `k1`, `b`, `avgdl` are
frozen with the segment; if they changed, the stored argmax could be
wrong (see C.5).

Query time (`search.rs:137-282`), three collections as in Lucene's
`WANDScorer`: `head` (heap by doc id), `lead` (cursors on the pivot),
`tail` (behind the pivot):

1. Term stage — pop cursors from `head` in doc-id order, accumulating
   `token_upper_bound` (the term-level bound, `search.rs:363`) until
   the running sum beats the current top-k threshold; that cursor's doc
   is the pivot (`search.rs:152-169`).
2. Block stage — `seek_block` every tail cursor to the pivot's block
   *without decoding it* (`search.rs:412-431`: it walks the summaries
   tape until `max_document_id ≥ target` and refreshes
   `block_upper_bound` from the summary's pair). If the sum of the
   **block** bounds of `tail ∪ lead` is still not competitive
   (`search.rs:194-204`), skip to `1 + min(block max doc id)` or the
   next head doc, advancing the cursor with the largest term bound
   (`search.rs:244-276`).
3. Otherwise `seek` (now decoding the block, `fill_block`,
   `search.rs:498-518`), fetch the document tuple for its exact
   `fieldnorm`, apply the filter callback, score every cursor, push
   into the bounded heap whose k-th score is the threshold
   (`search.rs:218-243`, `Results::push` :302-310).

Summaries have **no skip structure of their own**: a cursor reads them
sequentially through a `TruncatedTapeReader` sized `df / 128`
(`search.rs:365-380`, `tape.rs:202-232`). Block metadata is read from a
different tape than block bodies — the separation that lets the loop
decide competitiveness before paying for a decode.

### A.6 The build path and `segment_growing_max_page_size`

`ambuild` (`am_build.rs:128-316`): a parallel heap scan
(`table_beginscan_parallel`, :161, :596); each participant writes two
temp files — records `(dl, ctid)` and mappings `(key16, doc, tf)`
(`segment.rs:21, 25`; `io.rs:69-96`) — sorting mappings in **64 MiB
in-memory runs** (`io.rs:184`) and k-way merging 32 runs at a time
(`io.rs:199-241`); the leader merges the participants' streams,
offsetting doc ids per participant (`io.rs:244-282`, :143, :162) and
calls `bm25::build` (`am_build.rs:313`). Memory is bounded by the run
size, not the corpus; the sorted `(term, doc)` stream is what lets
`flush` emit blocks with a single forward pass. There is no
`segment_growing_max_page_size` in this tree (A.2).

### A.7 WHERE and JOIN: does the index scan support filters?

- The AM is `amcanorderbyop` (`am/mod.rs:149`) with cost forced to
  zero whenever an `ORDER BY … <&> …` matches (`am/mod.rs:252-257`), so
  the planner takes it. `amgettuple` returns at most `bm25.limit`
  ctids (`scanners/default.rs:114-118`; the GUC/reloption defaults to 0
  and a zero limit errors, `gucs.rs:20, 117-131`), so **every query is
  top-`limit` by index score; a `WHERE` on the same scan is applied
  by Postgres afterwards** — the classic post-filter loss.
  `tests/sqllogictest/prefilter.slt:28-46` pins it: `LIMIT 10 WHERE
  condition` with `bm25.limit = 3` returns 2 rows.
- `bm25.prefilter = on` passes a callback into the WAND loop
  (`scanners/default.rs:120-128`) that fetches the heap tuple by ctid
  and evaluates the *scan node's* quals (`fetcher.rs:180-215`, via an
  `ExecutorStart` hook that captures the `IndexScanState`,
  `hook.rs:16-72`). Filtering therefore happens per fully-scored
  candidate, only for quals attached to that scan node — not join
  quals, not quals the planner pushed elsewhere.
- Partial indexes are the other route (`bm25query.slt:27-30` builds
  `WHERE id % 2 = 0/1` indexes and the query must name the matching one).
- There is no index-side support for an id allow-list, an extension
  predicate, or a join; the index scan yields (score, ctid) and the
  executor does the rest.

### A.8 Claimed numbers

The README's benchmark section is **commented out** (README.md:385-428,
inside `<!-- -->`): QPS trec-covid 28.38 vs Elasticsearch 27.31,
webis-touche2020 38.57 vs 32.05; NDCG@10 67.67 / 68.80 / Lucene 61.0
and 31.0 / 34.70 / 33.2 — with the caveat that quality "is totally based
on the tokenizer". No index size, build time or bytes-per-posting are
published in the tree; the sizes in A.2 are computed from the format.

## B. pg_bestmatch.rs — BM25 as a sparse-vector dot product with no index of its own

### B.1 The design

Three pieces, all plain SQL plus two `pgrx` functions:

1. **Statistics = a materialized view** created by `bm25_create`
   (`src/sql/finalize.sql:22-68`): tokenize every row, `unnest` to
   tokens, `GROUP BY` for `how_many_tokens` (Σtf) and, over
   `array_distinct`, for `token_in_how_many_inputs` (df); emit one row
   per distinct token with `id = row_number() − 1` (:53) and
   `idf = ln((docs + 1) / (df + 0.5))` (:55), plus a btree on `token`
   (:60). The catalog row `pg_bm25` (:5-20) caches `words` (Σdl),
   `docs` (N), `dims` (vocabulary size), `b`, `k1`, tokenizer name.
   `bm25_refresh` is `REFRESH MATERIALIZED VIEW` plus a re-count
   (:70-87) — a whole rebuild.
2. **Document vector** (`src/lib.rs:39-140`): tokenize, look every
   token up in the view through the btree (one `index_rescan` per
   token, :62-97), count tf per id, then emit
   `id : tf / (tf + k1((1 − b) + b·dl/avgdl))` (:109, :126) — the
   tf-factor **without idf and without the (k1+1) numerator**, `dl`
   exact, `avgdl = words/docs` from the catalog.
3. **Query vector** (`src/lib.rs:143-231`): the same lookup, emitting
   `id : idf / Σidf` (:199-202, :215-218) — idf on the query side,
   normalised by the query's idf sum (a per-query constant, so ranking
   is unchanged; the linked pinecone-text issue explains the
   normalisation).

Score = dot product `<#>` between the two sparse vectors (README.md:119),
i.e. `Σ idf·tf/(tf+K) / Σidf` — BM25 minus the `(k1+1)` factor, scaled
by a query constant. The README says so: "Calculate the score by dot
product" (README.md:26-31).

### B.2 Where the scoring happens, and its limits

There is **no posting list anywhere**. Ranking is either a sequential
scan computing the dot product per row or an ANN index over the sparse
vectors (pgvecto.rs `svector` or pgvector `sparsevec`, README.md:103-108),
and the README's own warning is that HNSW "does not support the sparse
vectors generated by BM25 very well" (README.md:8-9). Limits that fall
out of the code:

- Token ids are `row_number()` over the sorted vocabulary (:53): any
  refresh that adds or removes a token renumbers every id after it,
  silently invalidating every stored document vector. The design only
  works if documents are re-vectorised after every refresh.
- Tokens are `NAME` (64 bytes, `RecordMat.token`, `src/lib.rs:31`) —
  the same 64-byte cap vfs chose.
- Vectorising a document costs one btree probe per token
  (`src/lib.rs:63-97`); building N document vectors is N × dl index
  scans, all inside one backend.
- `dims` = vocabulary size is the sparse vector's dimension; the
  vector types cap it (pgvector's `sparsevec` at 1 B dims), and the ANN
  indexes are approximate — top-k recall is not guaranteed.
- No per-document statistic is stored for reuse: `dl` is recomputed
  from the text at vectorisation time; nothing survives except the
  vector.

### B.3 What it teaches about a portable (no-AM) approach

- **The factorisation is the portable part.** BM25 splits into a
  document-side factor `tf/(tf+K(dl))` and a query-side factor `idf`
  with a dot product between them. pg_bestmatch puts idf on the query
  side so that a df drift only changes the *query* vector; vfs's
  `lex_terms.weight = idf·tfc` folds idf into the row, which is right
  for a whole-rebuild index (idf is frozen with the epoch) but would be
  the wrong side of the split for any incremental maintenance. A block
  row that stores `tf` and `dl` (or the tf-factor) and leaves idf to
  the query keeps both options.
- **Statistics as a separate keyed relation** — one row per term with
  `df`/`idf`, one catalog row with `N`/`Σdl`, probed by an `IN`-list —
  is exactly `lex_df` + `lex_stats`. Both projects and vfs converged on
  it; it is the part of BM25 that SQL does well.
- **What it lacks is the posting list**, and the consequence is a scan
  or an ANN index. It is the negative result: a term-statistics table
  alone gives correct scores but not a bounded query. The index that
  makes top-k bounded is the term-ordered posting list, which vfs's
  gram index already knows how to store as rows.
- **Vocabulary ids are fragile** when derived from a sort; if vfs ever
  takes fork E2 (term ids), the ids must be minted per epoch and never
  reused across epochs — or the term key can stay content-addressed as
  in VectorChord (A.1).

## C. Lucene — the default postings format, impacts, BM25, norms, and statistics across segments

### C.1 The current default: `Lucene104PostingsFormat`, 256-doc blocks

`Codec.java:59` names `Lucene104` the default codec and
`Lucene104Codec.java:121` its postings format. Block size is **256**
(`codecs/lucene104/ForUtil.java:34`; `Lucene104PostingsFormat.java:116-121`:
"a multiple of 64, currently fixed as 256 as a tradeoff … also the skip
interval"). Per term in the `.doc` file
(`Lucene104PostingsFormat.java:161-175`):

- `TermFreqs → <PackedBlock32>^(n/32), VIntBlock?`;
  `PackedBlock32 → Level1SkipData, <PackedBlock>^32`;
  `PackedBlock → Level0SkipData, PackedDocDeltaBlock, PackedFreqBlock?`.
- Doc deltas are FOR (one bit width per block, no patching); freqs are
  PFOR with up to 7 exceptions (`PForUtil.java:26-28`). Since 10.x the
  writer picks between FOR and a **bitset** for dense blocks: if the
  block spans exactly 256 doc ids it writes one byte, else it takes the
  bitset whenever it is no larger than the next bit width
  (`Lucene104PostingsWriter.java:429-463`).
- `Level0SkipData` per block = doc delta to the block's last doc
  (`writeVInt15`), the block's byte length, and the impacts
  (`:466-478`, `:392-408`); `Level1SkipData` every 32 blocks = 8,192
  docs (`:486-490`, `:497-539`; constants `Lucene104PostingsFormat.java:347-353`).
- A term with `df < 256` has no packed block at all: a VInt block, or a
  single doc id in the term dictionary (`SingletonDocID`, `:138-141`).
  Terms are held in the block tree (`codecs/lucene103/blocktree/`,
  25–48 entries per block, `Lucene103BlockTreeTermsWriter.java:217, 223`)
  with per-term `docFreq` and `totalTermFreq` (its header doc, `:120, 133`).

### C.2 Impacts: (freq, norm) pairs per block and per 32 blocks

While writing a block the writer feeds every posting's `(tf, norm)`
into a `CompetitiveImpactAccumulator`
(`Lucene104PostingsWriter.java:280-296`; the norm comes from the
segment's norms doc-values, defaulting to 1 when absent). The
accumulator keeps `maxFreqs[256]` — the maximum tf seen per norm byte —
and emits the **Pareto frontier**: walking norms upward, keep a pair
only if its max freq exceeds every lower norm's max freq
(`CompetitiveImpactAccumulator.java:64-72, 102-121`). The frontier is
serialised as freq/norm deltas (`writeImpacts`, `:540-556`) into the
level-0 skip entry; the level-1 accumulator is the union of its 32
blocks (`:481-484`). The reader decodes them lazily
(`Lucene104PostingsReader.java:1447-1470`) and exposes two levels
(`:1352-1400`: level 0 valid to `level0LastDocID`, level 1 to
`level1LastDocID`).

`Impacts.java:37-44` states the contract: pairs are sorted by
increasing freq and norm and "there is no guarantee that these impacts
actually appear in postings, only that they trigger scores that are
greater than or equal to the impacts that actually appear".

### C.3 How impacts become block-max WAND

- `MaxScoreCache.computeMaxScore` scores every pair of a level with the
  similarity's bulk scorer and takes the max (`MaxScoreCache.java:74-87`);
  `getSkipUpTo(minScore)` returns the last doc id of the deepest level
  whose max is still below the collector's minimum competitive score
  (`:137-158`), and `globalMaxScore = score(Float.MAX_VALUE, 1L)` is the
  bound when no level covers the target (`:48`).
- `ImpactsDISI.advanceTarget` (`ImpactsDISI.java:67-99`) calls
  `advanceShallow(target)` — which reads only skip data, not the block
  (`Lucene104PostingsReader.java:879-895`, `skipLevel0To` :818-872 seeks
  past a block's bytes when the target is beyond it) — takes
  `getMaxScoreForLevelZero`, and if it is below the threshold jumps to
  `getSkipUpTo + 1`, repeating; a block is decoded only when its bound
  is competitive.
- `WANDScorer` (`WANDScorer.java:28-53`) keeps `tail` / `lead` / `head`;
  `updateMaxScores` (`:436-486`) takes the next block boundary from
  the cheapest `head` clauses, refreshes every clause's `getMaxScore(upTo)`
  (block-max, not global max) and pops tail clauses into `head` while
  the tail's summed bound could still be competitive; `matches`
  (`:326-356`) advances tail clauses only while
  `leadScore + tailMaxScore ≥ minCompetitiveScore`. Scores are scaled
  to 24-bit integers, max scores rounded up and the threshold rounded
  down, so float error never drops a match (`:69-118`).

### C.4 `BM25Similarity`'s exact formula and the `cache[256]`

- `idf = log(1 + (docCount − docFreq + 0.5) / (docFreq + 0.5))`
  (`BM25Similarity.java:139-141`) — vfs's formula.
- `avgdl = sumTotalTermFreq / docCount` (`:144-146`).
- `LENGTH_TABLE[256] = byte4ToInt(i)` (`:149-154`); per query term
  `cache[i] = 1 / (k1((1 − b) + b·LENGTH_TABLE[i]/avgdl))` (`:215-221`).
- `score(freq, norm) = weight − weight / (1 + freq·cache[norm])` with
  `weight = boost·idf` (`:263-273`) — algebraically `idf·freq/(freq+K)`,
  **without the (k1+1) numerator** (dropped in Lucene 8); the rewrite
  is chosen so the score is monotone in both freq and norm under float
  rounding (`:258-265`), which the impacts machinery relies on.
- New in this tree: a `k3` query-side saturation
  `((k3+1)·qtf)/(k3+qtf)` for repeated query terms (`:114-121`),
  disabled by default.

**The norm.** `Similarity.computeNorm` stores
`SmallFloat.intToByte4(numTerms)` per document (`Similarity.java:151-160`),
one byte, in the norms file — not per posting. `intToByte4`
(`SmallFloat.java:147-157`): values below `NUM_FREE_VALUES = 255 −
longToInt4(Integer.MAX_VALUE) = 24` are exact; above, `24 +
longToInt4(i − 24)` keeps **4 significant bits** (3 stored + 1
implicit) with a shift (`:103-137`). Decoded, that is exact for
`dl ≤ 39` (the explain code says "approximate" above 39, `:319`),
then buckets of width `2^s` for values in `[8·2^s, 16·2^s)`: 40, 42, …,
54, 56, 60, …, 84, 88, 96, …, 144, 152, 168, …. Truncation, so the
error is one-sided: relative error `< 1/8`, in practice 2–6 % (dl 100 →
96, 1,000 → 984, 167 → 152 is the worst kind at ≈ 9 %). The error on
the *score* is smaller still: `K = k1(1 − b + b·dl/avgdl)` dilutes it
by `b`, and `tf/(tf+K)` again — a 10 % dl error moves a tf = 1,
dl ≈ avgdl score by ≈ 4 %. VectorChord's `FIELDNORM_TO_LENGTH` is this
exact table (A.4), so both engines rank with the same quantised dl.

### C.5 Is `max_tf` + `min_norm` per block a valid bound?

Yes, and it is the loosest of three valid choices. Write
`s(tf, dl) = idf · tf(k1+1) / (tf + k1(1 − b + b·dl/avgdl))`. For
`k1 ≥ 0`, `0 ≤ b ≤ 1`, `idf ≥ 0` (vfs's idf is never negative), `s` is
non-decreasing in `tf` and non-increasing in `dl`, so for every posting
in a block `s(tf_i, dl_i) ≤ s(max_i tf_i, min_i dl_i)`: **the pair
(max_tf, min_dl) is a valid upper bound whether or not any document has
both**. The three designs differ in how tight they make it:

1. `(max_tf, min_dl)` — one pair, possibly fictitious; valid for any
   `(k1, b, avgdl)` because it only uses monotonicity. Loosest.
2. Lucene — the Pareto frontier of observed pairs; the max over the
   frontier equals the max over the block's real postings for *any*
   monotone similarity. Tight, and independent of the scoring
   parameters, which matters to Lucene because the similarity is chosen
   at search time and per field. Cost: a variable-length list per block
   (at most 256 pairs, ≈ 2 bytes each, `Lucene104PostingsWriter.java:523`).
3. VectorChord — the single observed argmax pair under the frozen
   `(k1, b, avgdl)`. As tight as Lucene's, one pair; valid only while
   those parameters are frozen with the segment (A.5).

For a fixed formula the max score itself is the tightest and smallest
representation: one float. Lucene cannot store it because the formula
is not fixed at index time; vfs can (D.1).

### C.6 Statistics across segments: how idf sees the whole index

Lucene never merges postings across segments for scoring; it merges
the *statistics*:

- `TermStates.build` walks every leaf, seeks the term, and sums
  `docFreq` and `totalTermFreq` (`TermStates.java:96-121`,
  `accumulateStatistics` :158-164).
- `IndexSearcher.fieldStats` sums each leaf's `docCount`,
  `sumTotalTermFreq`, `sumDocFreq` (`IndexSearcher.java:1144-1158`);
  `termStats` wraps the summed term counts (`:1130-1132`).
- `TermQuery`'s weight builds one `SimScorer` from those index-wide
  stats (`TermQuery.java:60-81`), then scores each leaf with its own
  norms and impacts. Deleted-but-unmerged documents still count in
  both `docFreq` and `docCount` (the sums come from the term dictionary
  and field metadata, not live-doc bitmaps) — the accepted staleness
  until merge, the same trade VectorChord makes until VACUUM.

For vfs the analogue is trivial and already exists: one epoch, one
`lex_stats` row, one `lex_df` row per term; no per-leaf merge because
there is one leaf.

## D. Synthesis for vfs — a whole-rebuild-per-epoch index as `(epoch, term, block)` rows

### D.1 What a block row must carry for a valid, tight block-max bound

Because vfs rebuilds the whole index per epoch with `k1`, `b`, the
tokenizer, `idf` and `avg_dl` all frozen in the epoch (the options hash
forces a rebuild on any change), the per-block bound need not be a
`(tf, norm)` pair at all: it can be **the maximum stored weight in the
block**, computed once at build with the very same `term_weight`
function that scores at query time. That is Lucene's
`MaxScoreCache.computeMaxScore` output precomputed, or VectorChord's
`block_upper_bound` (`search.rs:381`) with the `evaluate` done at
flush. It is exact (equal to the true max over the block's postings),
one float, and — unlike VectorChord's pair — cannot go stale, because
the epoch that would change the parameters also rewrites the row.

The row, then:

| column | role | source of the idea |
|---|---|---|
| `epoch, term, block_no` (PK) | contiguous run per term, `block_no` ascending by doc id | grep's `(epoch, gram_key)` PK; Lucene's term-ordered `.doc` |
| `min_doc_id, max_doc_id` | seek/skip without decoding; `max_doc_id` is the `getDocIdUpTo(0)` / `block_max_document_id` | Lucene `Level0SkipData` doc delta; VectorChord `SummaryTuple` |
| `count` | postings in the block (tail blocks are short) | both |
| `max_weight` | the block-max bound (C.5) | Lucene impacts → `MaxScoreCache`; VectorChord `wand_*` pair |
| `postings` (blob) | d-gap doc ids + tf (+ dl or weight, D.3) bit/byte-packed; `encoding` tag as the gram table has | grep's delta+varint blob; Lucene FOR/PFOR; VectorChord bitpacking |
| `byte_size` | the cost ladder's fetch estimate | grep's `byte_size` |

And per term, in `lex_df`: `df`, `idf`, **`max_weight`** (the term-level
bound VectorChord keeps in `TokenTuple` and WAND's first stage needs,
`search.rs:161`), and `n_blocks`. `lex_stats` stays as it is.

Two-phase fetch, as grep already does (`grep.py:527-555`): first the
narrow columns `(term, block_no, min_doc_id, max_doc_id, count,
max_weight, byte_size)` for the query terms — this is VectorChord's
summaries tape and Lucene's skip data, read before any block body —
then block-max WAND over that metadata in Python/Rust decides which
blocks are competitive, and only those blobs are fetched by
`(term, block_no) IN (…)` under the membership budget. For a term
whose blocks all fit under a byte threshold, fetch metadata and blob in
one statement — the cost ladder decides, exactly as `_ladder_defers`
does for grams. The engine is asked only `WHERE epoch = ? AND term IN
(…)` and `… AND (term, block_no) IN (…)` (or `term = ? AND block_no IN
(…)` per term where row-value `IN` is not portable) — statements every
dialect plans as a PK seek, as the MSSQL spike showed for `lex_terms`.
Note the storage difference that makes the narrow select cheap:
Postgres TOASTs, InnoDB stores off-page, SQL Server and Oracle keep
LOBs out of row, so the metadata scan does not read blob pages; SQLite
stores the blob inline, so on SQLite the first phase reads blob pages
too — acceptable for the dev engine, and a reason to keep the blob the
*last* column.

### D.2 Block size: what the three converge on and why

- Lucene: 256 (`ForUtil.java:34`), up from 128 in 9.x; the comment
  gives the trade — smaller blocks, tighter bit widths and bounds;
  larger, more efficient bulk decode (`Lucene104PostingsFormat.java:116-121`).
  A second skip level every 32 blocks (8,192 docs).
- VectorChord: 128 (`flush.rs:82`), fixed by the SIMD kernel (128 ×
  u32 = 32 lanes of 4) and by `number_of_documents: u8`; no second level.
- pg_bestmatch: no blocks.

They converge on "a few hundred", because the block is the unit of
both the bound and the decode, and in both engines the block's
overhead is tiny (Lucene ≈ 5 bytes of skip data + impacts; VectorChord
a 24-byte summary + 16-byte header). **In SQL the unit is a row, and a
row costs 30–100 bytes of key and header** (`epoch` + a text `term`
up to 64 bytes + `block_no`, plus the engine's row header). That
pushes vfs's optimum *up*, not down: at 256 postings per block and
≈ 1.5 bytes per posting the blob is ≈ 400 bytes and the row overhead is
≈ 10–20 %; at 128 it approaches 30 %. Against that, a larger block
loosens the bound and enlarges the smallest fetch for a common term.
Two facts about vfs's corpus decide it: (a) vocabulary is Zipfian —
on the spec-130 sample 487 k distinct terms over 3.09 M postings, so
the overwhelming majority of terms have `df < 256` and are **one row
regardless of block size**, exactly Lucene's VInt-block/singleton case;
(b) the terms that do span many blocks are the common ones the MSSQL
spike identified as the multi-term cost, where block-max skipping is
the whole point and a 256-block keeps the metadata phase for a
`df = 1 M` term at ≈ 4 k narrow rows. **Start at 256** — Lucene's
number, the one that keeps the per-row overhead near 10 % — and let the
prototype benchmark measure 512 and 1,024 for the metadata-phase cost;
the bound quality degrades slowly, the row count halves each step.
Whatever the number, it belongs in `index_options_hash()`.

### D.3 Are quantized norms worth it when `dl` can be exact in `lex_docs`?

The question is really *where the query reads dl from*:

- **Lucene** stores one norm byte per document in a separate,
  randomly-addressable file and looks it up per scored posting
  (`cache[norm]`). SQL has no cheap random access into a 10 M-entry
  array; the equivalent is a `lex_docs` PK probe per candidate, i.e. a
  round trip per batch of candidates during the WAND loop — exactly the
  join the design is trying to leave.
- **VectorChord** stores the quantized `fieldnorm` per document in its
  documents tape and reads the document tuple per fully-scored
  candidate (`search.rs:218-229`) — a page read per candidate, which
  it can afford in-process.
- **pg_bestmatch** bakes `dl` into the document vector at
  vectorisation time; nothing is looked up at query time.

For vfs the blob should be **self-contained**: carry, per posting,
whatever the scorer needs so that the loop touches only the fetched
blobs and the query's `lex_df`/`lex_stats` rows. Three ways, in
increasing size:

1. `(doc gap, tf, dl_byte)` with Lucene's `byte4` encoding — ≈ 1 + ~0.4
   + 1 byte, and since chunks are near-uniform in length the dl bytes
   bit-pack to 3–5 bits. Scoring uses a 256-entry `cache` per term.
   Cost: the ranking becomes Lucene/tantivy/VectorChord's quantised
   ranking — the fidelity referee (τ = 1.0 against exact BM25) would
   have to accept the 2–6 % dl truncation.
2. `(doc gap, tf, dl)` with `dl` **exact**, bit-packed as an offset
   from the block's minimum dl — chunk lengths cluster, so this is
   ≈ 8–10 bits, not 32. Byte-identical scores to today's tables and
   the referee stays at τ = 1.0. ≈ 2.5 bytes per posting.
3. `(doc gap, weight as f32)` — 5 bytes, no scoring at all at query
   time; loses the tf/dl factorisation (B.3) and quantises the weight
   to float32 anyway.

Recommendation: **option 2** — exact `dl` per posting inside the blob,
`lex_docs` retained only for the build, MaxP joins, and liveness, not
for scoring. Quantized norms buy ≈ 1 byte per posting against a
duplicate `dl` per posting; the duplication is the price of leaving the
join, and at ≈ 2.5 bytes per posting the index is already 15× smaller
than the 40-byte row. If the byte budget ever matters more than the
referee, option 1 is a one-line encoder change and the cache table is
already written (`bm25.rs:15-272` shows the exact values Lucene
decodes to). Keep idf out of the blob either way (B.3): the stored
factor is the document side; `idf` is multiplied in from `lex_df` at
query time, so `max_weight` on the block row is `idf · max tf-factor`
and can be recomputed by the same code path that scores.

### D.4 Structural (borrowable) vs. tied to an index access method

Borrowable — ideas that are about the data, not the host:

- Term-ordered posting runs cut into fixed-size blocks with a
  per-block `(min_doc, max_doc, bound)` header separate from the body
  (Lucene skip data; VectorChord summaries tape). In SQL: the narrow
  columns of the block row, read first.
- The two-stage WAND (term bound, then block bound, then decode) with
  a k-th-score threshold heap — `search.rs:137-282` and
  `WANDScorer.java:436-486` are both plain in-memory algorithms over
  cursors; vfs runs it client-side over fetched metadata and blobs, in
  Rust behind `vfs.native` with the pure fallback, as the gram
  intersection already is.
- The bound-precomputed-at-build principle (VectorChord's `Wand::push`
  under a frozen `avgdl`), taken one step further because vfs freezes
  everything per epoch: store the max weight itself (D.1).
- Frozen corpus statistics per segment/epoch, with staleness accepted
  until the next rebuild (VectorChord until VACUUM, Lucene until merge,
  vfs until reindex) — vfs's `lex_df`/`lex_stats` are already this.
- Bit-packed d-gaps with one width per block, exceptions for freqs,
  byte-packing for short tail blocks; the dense-block bitset trick.
  All go into the Rust encoder beside `postings.rs`; the pure fallback
  can decode any of them with numpy as `decode_postings` does.
- Content-addressed 16-byte term keys with a per-epoch seed (A.1) as
  an alternative to fork E2's integer ids: no vocabulary lookup on the
  write path, fixed-width PK, and no id fragility (B.2).
- External-sort build with bounded in-memory runs (`io.rs:184`) — the
  answer to spec 130's "two passes to stay out of memory": sort
  `(term, doc, tf, dl)` runs to temp files and merge once, emitting
  each term's blocks in one forward pass; `flush.rs:73-136` is the
  shape.
- pg_bestmatch's split of idf to the query side (B.3).

Tied to an index AM — not available, and not needed:

- Postgres page tapes, `ambuild` parallel heap scans, `aminsert`,
  `amvacuumcleanup`, the `ExecutorStart` hook that smuggles quals into
  the scan (`hook.rs`), `amcostestimate` forcing the plan. vfs has its
  own equivalents: the reindex lease and epoch publish/reclaim, the
  offload pool, and scope pushed down as an id allow-list or a
  predicate on the entries side, decided by the cost ladder.
- Lucene's per-segment norms file and doc-values random access
  (replaced by D.3's in-blob dl), the block-tree term dictionary
  (replaced by the PK on `term`), per-field similarities (vfs has one
  formula per epoch, which is what makes D.1's float bound legal).
- VectorChord's top-`limit` cut-off inside the index and the
  post-filter loss that comes with it (A.7). vfs's loop owns the
  candidate set and applies liveness, extension, segment and allow-list
  scope before the threshold moves — the MSSQL spike's shapes S2–S7 —
  so the bound-based skipping and the scope never fight.

## Sources

- `~/Git/Repos/VectorChord-bm25` @ 14fc2a3 (`main`, refreshed 2026-08-26;
  AGPL-3.0 / Elastic License 2.0 dual) — `crates/bm25/src/{bm25,search,
  flush,build,maintain,insert,bulkdelete,compression,io,segment,vector,
  tuples,tape}.rs`, `crates/simd/src/bitpacking_u32_ordered.rs`,
  `src/index/{gucs,hook,fetcher,operators,storage}.rs`,
  `src/index/bm25/am/{mod,am_build,am_vacuumcleanup}.rs`,
  `src/index/bm25/scanners/default.rs`, `src/datatype/tsvector.rs`,
  `src/sql/finalize.sql`, `sql/install/vchord_bm25--0.3.0.sql`,
  `tests/sqllogictest/{bm25query,prefilter}.slt`, `README.md`.
- `~/Git/Repos/pg_bestmatch.rs` @ 0a3b574 (`main`, refreshed 2026-08-26;
  Apache-2.0) — `src/lib.rs`, `src/sql/finalize.sql`,
  `src/tokenizer/mod.rs`, `README.md`.
- `~/Git/Repos/lucene` @ 0cc09c8 (`main`, refreshed 2026-08-26;
  Apache-2.0) — `codecs/Codec.java`, `codecs/lucene104/{Lucene104Codec,
  Lucene104PostingsFormat,Lucene104PostingsWriter,Lucene104PostingsReader,
  ForUtil,PForUtil}.java`, `codecs/{CompetitiveImpactAccumulator,Impact}.java`,
  `codecs/lucene103/blocktree/Lucene103BlockTreeTermsWriter.java`,
  `index/{Impacts,FreqAndNormBuffer,TermStates}.java`,
  `search/{ImpactsDISI,MaxScoreCache,WANDScorer,IndexSearcher,TermQuery}.java`,
  `search/similarities/{BM25Similarity,Similarity}.java`,
  `util/SmallFloat.java`.
- In-tree: `context/specs/archive/130-lexical-index-and-tokenizer/spec.md`,
  `context/research/2026-08-26-bm25-vs-mssql-fulltext.md`,
  `src/vfs/models/{postings,lexical,rows}.py`,
  `src/vfs/storage/backends/database/{indexing,lexical,grep}.py`,
  `crates/vfs-core/src/postings.rs`.
- Studied read-only; no code copied. Date: 2026-08-26.
