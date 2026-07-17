# Analysis — VFS code-gram index design vs. Russ Cox's `google/codesearch`

> Date: 2026-05-25
> Reviewer scope: validate story 013's database-backed trigram index design
> against the closest proven architectural match, Russ Cox's `codesearch`.
> Source repo studied: `/Users/claygendron/Git/Repos/codesearch` (index v2 format).
> This file is analysis only; it does not edit spec.md /
> implementation.md / research.md.

`codesearch` is a build-once-then-merge, mmap'd flat-file index. VFS is a
live, mutable, multi-backend relational index with per-write edits and deletes.
The two share the *same logical core* — doc-level (not positional) trigram
inverted index, Cox-style filter -> candidate set -> verify with the real regex —
but diverge wherever "immutable file rebuilt offline" vs. "mutable rows updated
transactionally" forces a different mechanism. Most VFS divergences are
justified by that difference; two are worth flagging.

---

## Findings (concrete, with citations)

### F1. Trigram extraction: raw bytes, sliding window, deduped per file, NUL/UTF-8/length/trigram-count skips

`index/write.go:215-295` (`IndexWriter.add`) is the indexer. Mechanics:

- Trigrams are a 24-bit value built by `tv = (tv << 8) & (1<<24-1); tv |= c`
  (`write.go:226,243`) — a sliding window over **raw input bytes**, started only
  once `n >= 3` (`write.go:244`). Identical primitive to VFS's
  `pack_gram(b0,b1,b2) = (b0<<16)|(b1<<8)|b2` (spec.md §Gram Key) and
  `iter_code_grams` (implementation.md §code_grams.py).
- **Dedup per file is intrinsic:** trigrams accumulate into `ix.trigram`, a
  `sparse.Set` over `1<<24` (`write.go:44,72`), then emitted via
  `ix.trigram.Dense()` (`write.go:288`). A set, so each distinct trigram appears
  once per file. Matches VFS's "deduplicate grams per chunk before storage"
  (spec.md §Scope item 1).
- **No casefolding.** `add` stores the raw bytes; there is no `casefold`/
  `ToLower` anywhere in `write.go`. Case-insensitivity is handled entirely at
  *query* time (see F6). This is the single biggest tokenizer-level divergence
  from VFS (see C2).
- **File skip limits** (`write.go:126-135, 247-280`), all "not text, don't
  index" guards:
  - `maxFileLen = 1<<30` (1 GB) (`write.go:132,259`)
  - `maxLineLen = 2000` bytes per line (`write.go:133,265`)
  - `maxTextTrigrams = 20000` distinct trigrams per file (`write.go:134,275`) —
    this is the famous "too many trigrams => probably not text" limit Sourcegraph
    documents at 20k (research.md cites it). Checked *after* the whole file is
    read, against `ix.trigram.Len()`.
  - NUL byte => skip (`write.go:247`); invalid UTF-8 byte-pair => skip
    (`write.go:253`, `validUTF8` at `write.go:752-765`).

  Note the limit is **per file**, and on hit the file is *dropped from the index
  entirely* — it is not a "cap the grams" but a "don't index this document"
  decision. VFS lists "file skip limits for high unique-gram files" as a
  mitigation (spec.md §Risks) but has **not** specified a concrete threshold or
  the drop-the-doc semantics. See P1.

### F2. File IDs: dense, sequential, assigned in sorted-name order at build time

- `addName` (`write.go:376-390`) assigns `id := ix.numName; ix.numName++` — a
  **dense 0-based auto-increment**, assigned in the order files are added.
- Files are added in **sorted path order** (the `cindex` walker sorts roots
  `slices.SortFunc(roots, index.Path.Compare)` at `cmd/cindex/cindex.go:117`,
  and v2 enforces names strictly increasing: `addName` fatals if
  `name.Compare(ix.nameLast) <= 0`, `write.go:381`). So fileid order == sorted
  path order.
- A `postEntry` is a `uint64` packing `(trigram<<40) | fileid` (`write.go:101,
  117-124`), capping fileids at 2^40 and trigrams in the top 24 bits.
- **Renumbering happens on every merge.** `Merge` builds `idrange` maps that
  translate old fileids into a fresh contiguous C-space (`merge.go:39-118`,
  applied in `postMapReader.nextId` at `merge.go:359-383`). codesearch's fileids
  are explicitly **not stable across rebuilds/merges** — every incremental update
  renumbers.

This is the sharpest contrast with VFS: VFS keeps a **stable, never-renumbered**
`doc_id` (spec.md §Data Model -> Doc IDs), tolerating gaps, precisely because it
must support in-place edits and deletes against a live index without rewriting
the world. codesearch can renumber freely because it always rewrites the whole
file. See C1 — VFS's choice is correct *for its constraints*, and codesearch's
behavior actively validates the "sorted is mandatory, dense is only a bonus"
reasoning.

### F3. On-disk posting-list serialization: sorted IDs, gap (delta) encoding, terminating zero

The format spec is the comment block at `index/read.go:31-46`:

> Each posting list has the form: `trigram [3]` then `deltas [v]...`. The delta
> list is a sequence of gamma-coded deltas between file IDs, **ending with a zero
> delta**. `[2,5,1,1,0]` encodes file IDs `1,6,7,8`.

Writer side (`write.go:823-902`, `postDataWriter`):

- `trigram(t)` writes the 3 raw trigram bytes (`WriteTrigram`, `write.go:694`).
- `fileid(id)` writes `delta.Write(id - w.lastID)` (`write.go:867-871`) — a
  **gap from the previous id**, exactly VFS's "delta (gap) encode" (spec.md
  §Posting-block compression).
- `endTrigram` writes a terminating `0` delta (`write.go:874`).

**Encoding has two versions, and v2 deliberately moved off varint:**

- v1: plain unsigned varint of each gap (`delta.go:108-110`, the
  `writeVersion==1` branch). This is *exactly* VFS's proposed v1 encoding
  ("delta (gap) encode -> varint encode").
- v2 (current default, `merge.go:46` `writeVersion = 2`): **Elias gamma-coding**
  (`delta.go:113-137` `writeBits`, read at `delta.go:51-83` `next64`). Because
  gamma-coding can't represent 0, the terminating/zero gap is remapped:
  `deltaZeroEnc = 16` (`delta.go:31`), values `>=16` are bumped by one on write
  (`delta.go:99-104`) and un-bumped on read (`delta.go:33-49`).
- The measured payoff is documented in-file (`read.go:121-144`): on the Linux
  kernel tree, the v1->v2 tighter encodings cut total index size **>40%**
  (157.7 MB -> 89.4 MB), and on 1.6 TB of Go module zips, **162 GB -> 84 GB**,
  with posting lists alone 132.7 GB -> 80.3 GB.

VFS's spec already anticipates exactly this evolution: it has an `encoding`
field per block "so the format can evolve per-block" and explicitly names
"Roaring bitmaps, frame-of-reference / SIMD-BP128, EWAH" as upgrades (spec.md
§Posting-block compression). codesearch is direct empirical evidence that (a)
delta+varint is the right *starting* point and (b) a denser bit-packed code
(gamma here) is the right *next* step, worth ~40-50% — i.e. the per-block
`encoding` field is not over-engineering. See P2 (cite this number in the spec
to justify the field) and C3.

### F4. The posting-list *index* (find a trigram fast): 256-byte blocks, binary search, mmap

VFS's spec leans on `min_doc_id`/`max_doc_id` per block for "block skipping" and
gram statistics for rarest-first ordering. codesearch's analogue is a separate
**posting-list index** keyed by trigram:

- The whole index file is **mmap'd** (`read.go:196-197,653-660` + the
  per-OS `mmap_*.go`); all reads are slices into that mapping
  (`read.go:244-257` `slice`). No decompress-to-heap step; reads stream out of
  the mapped delta bytes.
- Each posting-index entry is `trigram[3], file-count[v], offset[v]`
  (`read.go:51-63`). Entries are packed into **256-byte blocks**
  (`postBlockSize = 256`, `read.go:165`); any entry that would cross a 256-byte
  boundary is zero-padded to the next boundary (`write.go:893-901`) so that
  **random access via binary search over blocks works** despite the varint'd
  contents.
- Lookup: `findListV2` (`read.go:369-403`) binary-searches the blocks by leading
  trigram, then linear-scans within the 256-byte block. `count == 0` => trigram
  absent => empty list. Empty posting lists are simply **never written**
  (`read.go:66-76`: "the majority of possible trigrams are never seen, so
  omitting the missing ones represents a significant storage savings").

The conceptual match to VFS is: codesearch's `(trigram, count, offset)` index
entry ~= VFS's gram-statistics row (`gram_key, doc_freq, block_count`) plus the
block locator. `count` is literally the per-gram document frequency VFS wants
for rarest-first planning (spec.md §"Gram statistics"). The "don't store empty
lists" rule is VFS's "gaps tolerated, missing grams never materialized" by
another name. No change needed — this *confirms* VFS's statistics table is the
right shape; see C4.

### F5. Read path: posting-list AND/OR is a linear merge of sorted int lists, with a `restrict` carry

`index/read.go:505-636`:

- `postingList(trigram, restrict)` decodes a single list (`postReader`,
  `read.go:405-461`), reconstructing ids by accumulating gaps
  (`r.fileid += delta`, `read.go:441`).
- **AND** = `postingAnd` (`read.go:519-535`): walks the new list against the
  running `list` with a single advancing cursor `i` — a **linear two-pointer
  merge of two sorted int lists**, O(n+m). Result reuses `list[:0]` storage.
- **OR** = `postingOr` (`read.go:541-559`) / `mergeOr` (`read.go:617-636`):
  standard sorted-list union.
- **`restrict`** (`read.go:410,442-451`): an optional already-narrowed candidate
  set threaded through the reader so an AND can skip ids outside the running
  candidate set *while decoding*, rather than decoding the full list then
  intersecting. This is a coarse form of the "skip optimization" — it doesn't use
  the `min/max` block bounds VFS proposes (codesearch decodes sequentially
  because gamma-coding isn't randomly seekable mid-list), but it prunes by the
  running candidate set.
- `postingQuery` (`read.go:565-615`) is the AND/OR tree evaluator over a `Query`
  (see F6). `QAll` materializes `0..numName` (`read.go:573-577`); `QNone`
  returns nothing.

This is the linear-merge intersection VFS describes ("that same ordering is what
lets posting-list intersection run as a linear merge", spec.md §Doc IDs). The
read path is out of scope for story 013, but it confirms *why* sorted integer
doc_ids are non-negotiable: every set operation here depends on both lists being
sorted ascending. See C1.

### F6. regex->trigram query compilation: a 4-op boolean `Query`, conservative, with strong simplification

`index/regexp.go` is the analogue of VFS's `code_grams.py` planner.

- The query type (`regexp.go:22-35`): `Query{Op, Trigram []string, Sub []*Query}`
  with ops `QAll` (everything matches — the scan fallback), `QNone` (nothing),
  `QAnd`, `QOr`. This maps **directly** onto VFS's `GramAny` / `GramAnd` /
  `GramOr` tiers (implementation.md §code_grams.py) — VFS's `ANY` == codesearch `QAll`; VFS has no
  explicit `QNone` (a regex that matches nothing), a minor and harmless omission.
- **Soundness contract is identical:** the doc comment (`regexp.go:15-21`) — "a
  conservative version of the regexp: it matches everything the regexp would
  match, and probably quite a bit more" — is precisely VFS's "false positives
  OK; false negatives forbidden" (implementation.md §code_grams.py).
- Compilation is over the **regex AST**, not the raw pattern string:
  `RegexpQuery(re *syntax.Regexp)` walks `regexp/syntax` ops in `analyze`
  (`regexp.go:333-540`). This is the same architectural decision VFS made and
  documents as load-bearing for soundness — VFS walks Python's `sre_parse` AST
  (implementation.md: "traverses `sre_parse` AST rather than hand-rolling a
  tokenizer. Eliminated every false-negative bug"). **Strong cross-validation:
  the reference implementation reaches for the AST for the same reason.**
- Per-op handling worth noting for the VFS planner:
  - `OpLiteral` -> exact set, ANDed trigrams (`regexp.go:434-468, 626-630`).
  - `OpConcat` -> `concat` crosses suffix x prefix sets and `andTrigrams` the
    boundary-spanning trigrams (`regexp.go:558-597`) — i.e. it *recovers
    trigrams that straddle two concatenated pieces*, which a naive "trigrams of
    each literal" planner would miss. Worth checking VFS's planner does the
    same for concatenated literal runs.
  - `OpAlternate` -> `alternate` builds the OR (`regexp.go:600-623`).
  - `OpStar`, `OpRepeat` with `Min==0`, `OpAnyChar` -> `anyMatch`/`anyChar` =>
    `QAll` (`regexp.go:470,485-493`) — the mandatory degrade-to-scan path.
  - `OpCharClass` larger than 100 runes => `anyChar` (`regexp.go:524-527`) — caps
    alternation blowup, an overestimate that stays sound.
- **Boolean simplification is substantial and is where VFS's planner is
  weakest.** `andOr` (`regexp.go:52-170`) does implication-based pruning
  (`q.implies(r)` => drop redundant clause, `regexp.go:71-84,174-224`), merges
  same-op nodes, and **factors common trigrams** out of an AND-of-ORs /
  OR-of-ANDs (`regexp.go:117-166`, the worked rewrite
  `(abc|def|ghi|jkl) AND (abc|def|mno|prs) => (abc|def) OR ((ghi|jkl) AND
  (mno|prs))`). `maxExact=7`, `maxSet=20` (`regexp.go:368,377`) bound the
  combinatorial sets. VFS's plan explicitly says "Start conservative ... return
  `ANY` for hard patterns" (implementation.md §code_grams.py, shipped) — correct as an MVP, but codesearch
  shows the selectivity headroom left on the table. This is query-side (out of
  scope for 013) so it is *not* a proposed spec edit; flag for the query story.

### F7. The verify step: a byte-at-a-time lazy-DFA matcher, line-oriented

`regexp/match.go` is the authoritative final matcher (VFS's "Python/ripgrep-style
final match").

- It is a **custom lazy DFA** built from `regexp/syntax.Prog` (`match.go:24-30,
  131-148`), with on-demand state construction cached by encoded NFA state
  (`match.go:269-281` `cache`, `computeNext` at `match.go:213-267`). It matches
  **one byte at a time** (`match.go:283-340` `match`/`matchString`), so it
  operates on raw bytes exactly like the byte-trigram index.
- **Case-insensitivity is enforced here, in the matcher**, via the `argFold`
  instruction flag: `stepByte` folds `'a'..'z'` to upper before range-checking
  (`match.go:179-181`). This is the byte-level counterpart of the regex-AST
  `FoldCase` handling in `regexp.go:435-466`. So codesearch's case story is:
  raw-byte index + case-folding pushed entirely into the *query expansion* and
  the *verifier* — never into the stored grams.
- Matching is **line-scoped**: the DFA resets at `\n` (`match.go:295-299`,
  `startLine`), and `Reader` (`match.go:432-548`) drives it over a 1 MB buffer
  with line-context bookkeeping. The verifier is the semantic authority; the
  index only ever produces candidate files. This is identical in spirit to VFS's
  "the index is never the semantic authority ... only a safe superset generator"
  (research.md §Recommended Canonical Tokenizer).

### F8. Incremental indexing / "merge", and the absence of deletes

`index/merge.go` + `cmd/cindex/cindex.go:120-186`:

- codesearch's *entire* incremental story is **rebuild-a-subset-then-merge-two-
  whole-indexes**. `cindex` with no args "reindexes the paths that have already
  been added, in case the files have changed" (`cindex.go:38-40`) — i.e. a full
  re-walk. The doc comment in `write.go:33-36` is explicit: building a subset
  index and merging it into an existing one "would allow incremental updating ...
  **But we have not implemented that.**"
- `Merge(dst, src1, src2)` (`merge.go:51-282`): src2 is newer and *shadows* src1
  for any overlapping root (`merge.go:62-109`). Updating a directory = re-index
  that directory into a fresh index, then merge, where the new root's range
  **replaces** (`15-24 is deleted`, `merge.go:18`) the old fileids for that
  root.
- **There is no per-document delete and no tombstone.** Deletion only happens at
  *root-range granularity during a merge* (`idrange` with no `new` target =>
  dropped, `merge.go:106-108`). A single changed/removed file is handled by
  re-indexing and merging its whole root, then **renumbering everything**
  (F2). There is nothing resembling VFS's staged `delete` deltas, latest-action-
  wins folding, or Lucene-style `liveDocs` tombstones.

This is the deepest architectural divergence, and it is **fully justified**:
codesearch is a CLI over a static corpus snapshot rebuilt by a nightly cron
(`cindex.go:38-40` literally suggests cron); VFS is a live database with
per-write edits and hard deletes that *cannot* rewrite the whole index per edit.
VFS's staging-delta-log + latest-action-wins + copy-on-write compaction (spec.md
§Durable Storage Model) is the *correct generalization* of codesearch's
build-once model into a mutable one — it is solving a problem codesearch
explicitly punted on. See C1/C5.

### F9. Build pipeline: in-memory radix-sorted runs flushed to temp files, then heap-merged — this is SPIMI/BSBI

`write.go:288-455`:

- `add` appends `(trigram, fileid)` postEntries to an in-memory slice `ix.post`
  capped at `npost = 64MB/8` entries (`write.go:67,289`).
- When full, `flushPost` (`write.go:394-424`) radix-sorts the run (`sortPost`,
  two 12-bit passes, `write.go:776-821`) and writes it to a temp file as
  per-trigram delta-encoded lists.
- `mergePost` (`write.go:428-455`) k-way-merges the sorted temp runs plus the
  final in-memory run via a `postHeap` priority queue (`write.go:466-590`),
  producing the final posting lists.

This is exactly the **SPIMI / BSBI block-sort-merge index construction** VFS
cites (research.md §Design Conclusion: "single-pass in-memory indexing (SPIMI)
followed by block merging — Manning, Raghavan & Schutze ch. 4"). VFS's
"staging -> periodic flush -> posting blocks -> compaction merge" is the
*database-resident, mutable* form of this same pipeline. **codesearch is the
canonical reference implementation of the build pipeline VFS's research section
names.** See C5.

---

## Confirms / Contradicts

### Confirms (VFS matches codesearch's proven choices)

- **C1 — Sorted-integer doc IDs are mandatory; the doc-level model is right.**
  codesearch's fileids are dense sorted ints; every posting list is a gap-delta
  list of them (F3); every AND/OR is a linear merge that *requires* sorted order
  (F5). This directly validates VFS's central §Doc IDs decision and the
  "sorted is mandatory, dense is a bonus" framing. (VFS keeps them *stable*;
  codesearch renumbers — see D1, justified.)
- **C2/F6 — Cox-style filter->candidate->verify with an AST-driven, conservative,
  4-op boolean query.** VFS's `GramAny/And/Or` <-> codesearch `QAll/QAnd/QOr`,
  same soundness contract, same "walk the AST not the string" decision (F6, F7).
  Confirmed in detail.
- **C3 — Delta + varint as the v1 encoding, with a per-block `encoding` field
  for later densification.** codesearch shipped delta+varint (v1) then moved to
  gamma-coding (v2) for a ~40-50% size win (F3). VFS's `encoding` field and
  "start simple, let benchmarks drive the format" is exactly this trajectory,
  now with hard numbers behind it.
- **C4 — Per-gram document-frequency statistics + omit empty lists.**
  codesearch stores `(trigram, count, offset)` and never writes empty posting
  lists (F4). VFS's gram-statistics table (`gram_key, doc_freq, block_count`)
  and "missing grams never materialized" match this.
- **C5 — staging->flush->blocks->merge is SPIMI/BSBI; immutable-segment + merge is
  the right scaling model.** codesearch *is* the reference SPIMI build (F9) and
  its merge is segment-style (F8). VFS's pipeline is the mutable, DB-resident
  generalization. Confirmed.
- **C6 — Dedup trigrams per document; skip non-text files by a unique-trigram
  ceiling.** codesearch dedups via a set and drops files over 20k distinct
  trigrams (F1). VFS dedups per chunk and lists file-skip limits as a
  mitigation. Confirmed in principle (but VFS hasn't pinned the threshold — P1).

### Contradicts / Diverges (and whether justified)

- **D1 — Stable, never-renumbered doc_ids (VFS) vs. renumber-on-every-merge
  (codesearch). JUSTIFIED.** codesearch can renumber because it rewrites the
  whole file offline (F2, F8). VFS must support in-place edits/deletes against a
  live multi-backend store without a global rewrite, so stable ids + tolerated
  gaps + rare full-reindex (spec.md §Doc IDs) is the correct adaptation. The
  divergence is forced by VFS being mutable; codesearch's behavior is *evidence
  for* VFS's reasoning, not against it.
- **D2 — Casefolded single lowercase stream (VFS) vs. raw-byte index with case
  handled only at query+verify time (codesearch). JUSTIFIED, but note the
  asymmetry.** codesearch stores raw bytes and folds case in the regex expansion
  (`regexp.go:435-466`) and the verifier (`match.go:179-181`) — F1, F6, F7. VFS
  instead **casefolds the stored grams** into one lowercase stream and verifies
  case in Python (spec.md §Normalization). Both are sound. The trade differs:
  - codesearch's raw index gives *better selectivity* for case-sensitive queries
    (the common code-search default) at the cost of expanding case-insensitive
    queries into larger OR-of-trigram sets at query time.
  - VFS's folded index gives *smaller storage* (~1/2) and trivial
    case-insensitive queries, at the cost of broader candidate sets for
    case-*sensitive* queries.

  VFS's choice is defensible and well-documented (spec.md §Risks "Case-
  insensitive candidate breadth", Open Question 2 resolved). The thing to be
  aware of: codesearch's authors chose the *opposite* default precisely because
  code search is usually case-sensitive, where a raw index is more selective.
  This is a genuine design fork, not a VFS error — but the spec's claim that
  folding is a near-pure win should be read against the fact that the reference
  implementation went the other way for a reason. See P3 (a wording tightening,
  not a redesign).
- **D3 — No per-document deletes/tombstones in codesearch.** Not a contradiction
  of VFS so much as a gap VFS *fills*. codesearch deletes only at root-range
  granularity during merge (F8). VFS's staged delete deltas + latest-action-wins
  + copy-on-write block re-encode is the mutable generalization. JUSTIFIED and
  necessary; codesearch offers no counter-evidence here, only confirmation that
  immutable blocks + merge is the substrate to build deletes on top of.
- **D4 — VFS has no `QNone` equivalent.** codesearch models "regex matches
  nothing" as `QNone` (`regexp.go:34,403`). VFS's tiers are `ANY/AND/OR` only
  (implementation.md §code_grams.py). Harmless — a never-matching pattern is rare and `ANY`
  (scan, find nothing) is still *correct*, just not optimal. Query-side, out of
  scope; noted for completeness, no spec edit proposed.

---

## Proposed edits

Only changes justifiable directly from the codesearch source. Each names the
target section and gives proposed wording. (These are proposals only; the
files are not edited here.)

### P1 — spec.md §Risks -> "Storage growth" and "Hot grams": pin a concrete unique-gram file-skip threshold with drop-the-document semantics

**Justification:** codesearch's `maxTextTrigrams = 20000` (`write.go:134`) is a
*hard, concrete* per-file ceiling, and on hit the file is **dropped from the
index entirely** (`write.go:275-280`), not merely capped. VFS twice lists "file
skip limits for high unique-gram files" as a mitigation (spec.md §Risks,
"Storage growth" and "Hot grams") but never states a number or the drop
semantics, leaving the mitigation unactionable.

**Proposed addition** (append to the "Storage growth" risk mitigation):

> Mitigation: dedupe per chunk, chunk size caps, compressed posting blocks, and
> a **concrete per-document unique-gram ceiling** (Google `codesearch` uses
> 20,000 distinct trigrams per file, `index/write.go:134`; a document exceeding
> it is treated as non-text and **excluded from the index entirely**, not
> truncated). VFS should set an analogous `MAX_UNIQUE_GRAMS_PER_CHUNK` and, on
> exceed, skip indexing that chunk's content (the final regex verify still scans
> it, so correctness is preserved — a skipped chunk is just never a *candidate*).
> The threshold is a benchmarked knob.

### P2 — spec.md §"Posting-block compression": cite codesearch's measured v1->v2 win to justify the `encoding` field

**Justification:** VFS asserts "Start simple (delta-varint) and let benchmarks
drive the format" and lists denser encodings as future upgrades behind the
`encoding` field, but cites no evidence that the upgrade is worth the
machinery. codesearch is direct evidence: delta+varint (v1) -> Elias gamma-coding
(v2) cut posting-list bytes from 132.7 GB -> 80.3 GB on 1.6 TB of Go modules and
total index size >40% on the Linux kernel (`index/read.go:121-144`).

**Proposed addition** (append to the paragraph ending "...let benchmarks drive the
format."):

> This staged path is proven: Google `codesearch` shipped delta+varint (its v1
> format) and later moved to Elias gamma-coded gaps (v2), measuring a
> posting-list reduction of 132.7 GB -> 80.3 GB on 1.6 TB of Go module zips and a
> >40% total index-size reduction on the Linux kernel tree
> (`index/read.go:121-144`). The per-block `encoding` field is what makes such an
> upgrade a per-block opt-in rather than a whole-index migration.

### P3 — spec.md §Risks -> "Case-insensitive candidate breadth": acknowledge the reference implementation's opposite default

**Justification:** spec.md frames the single folded stream as essentially a
free win ("Mitigation: none needed"). The reference implementation, codesearch,
deliberately keeps a **raw-byte** index and folds case only at query+verify time
(`index/write.go:add` stores raw bytes; `regexp.go:435-466` and
`match.go:179-181` handle folding), because the common code-search query is
*case-sensitive*, where a raw index is strictly more selective. VFS's choice is
still defensible (storage halving, trivial case-insensitive queries), but the
risk note overstates the certainty.

**Proposed rewording** of the "Case-insensitive candidate breadth" mitigation:

> Mitigation: the final regex check enforces case, so folding to one stream is
> always correct; it is a deliberate storage/selectivity trade (roughly halves
> index size vs. dual streams). Note the trade is genuinely two-sided: Google
> `codesearch` made the **opposite** choice — a raw-byte index, folding case
> only in the query expansion (`index/regexp.go:435-466`) and the verifier
> (`regexp/match.go:179-181`) — because the common code-search query is
> case-*sensitive*, where a raw index is more selective. VFS optimizes for
> storage and case-*insensitive* queries instead; if benchmarks show
> case-sensitive candidate breadth dominating, a raw stream can be added later
> by namespacing inside `index_id` (no schema migration — implementation.md
> §"Default case mode is folded").

### P4 — implementation.md §code_grams.py: record the concat boundary-trigram requirement as an explicit planner soundness/selectivity check

**Justification:** codesearch's `concat` recovers trigrams that *span the
boundary* between two concatenated regex pieces by crossing the suffix set of
the left with the prefix set of the right and `andTrigrams`-ing the result
(`index/regexp.go:558-597`, esp. the `x.suffix.cross(y.prefix)` boundary block
at `regexp.go:589-593`). A planner that only emits "trigrams of each literal
piece" is still *sound* but loses the boundary trigrams, weakening selectivity
for patterns like `foo` `+` `bar` whose strongest signal (`oob`, `oba`) lives at
the seam. This is query-side (out of scope for story 013), so the edit is a
*note*, not a contract change.

**Proposed addition** (a
note in implementation.md §code_grams.py):

> Planner selectivity note (query-side, tracked with the out-of-scope query
> work): when compiling a concatenation of literal runs, also emit the trigrams
> that **span the boundary** between adjacent runs (cross the left run's
> trailing 2 chars with the right run's leading chars), as Google `codesearch`
> does in `index/regexp.go:558-597`. Omitting them stays sound (no false
> negatives) but discards the most selective trigrams at each seam.

---

## One-paragraph bottom line

codesearch confirms VFS's core design across the board: doc-level trigram
inverted index, sorted-integer doc ids, gap+varint posting compression with a
clear path to a denser code, per-gram doc-frequency stats, omit-empty-lists,
conservative AST-driven boolean query compilation with a mandatory scan
fallback, and a final byte-level regex verifier as the sole semantic authority —
plus a SPIMI/BSBI build pipeline that is exactly VFS's staging->flush->blocks->merge
in immutable-file form. The real divergences (stable vs. renumbered doc ids; a
folded single stream vs. a raw index with query-time case folding; first-class
per-document deletes/tombstones vs. root-range merge deletes) are all forced by
VFS being a *live, mutable, multi-backend database* where codesearch is a
*rebuild-offline flat file*, and in each case VFS's choice is the correct
generalization rather than a mistake. The four proposed edits are
evidence-backed tightenings, not redesigns.
