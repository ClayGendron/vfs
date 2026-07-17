# Analysis — SQLite FTS5 vs. VFS Code-Trigram Index Design

> Date: 2026-05-25
> Reviewing: story 013 spec.md / implementation.md / research.md
> Source studied: /Users/claygendron/Git/Repos/sqlite/ext/fts5/
> Scope: validate VFS's storage / merge / compaction / tokenizer design against
> FTS5's proven mechanics, and against FTS5's role as a target SQLite backend.

All line numbers are from the SQLite checkout at
`/Users/claygendron/Git/Repos/sqlite/ext/fts5/`.

---

## Findings

### 1. Segment + level (LSM) structure

FTS5 is a log-structured merge index — exactly VFS's
staging -> flush -> immutable-blocks model.

- **Shadow tables.** Index data lives in two shadow tables:
  `%_data(id INTEGER PRIMARY KEY, block BLOB)` and `%_idx`.
  `fts5_index.c:82` declares `%_data`; the `%_idx` writer/deleter statements are
  at `fts5_index.c:369-370` (`pIdxWriter` = `INSERT ... %_idx VALUES`,
  `pIdxDeleter` = `DELETE FROM %_idx WHERE segid=?`). FTS5 stores **opaque
  compressed blobs keyed by an integer rowid** — structurally identical to VFS's
  `postings` blob keyed per `(gram_key, block_id)`.

- **Structure record.** One record holds the whole index shape: a config cookie,
  then `nLevel`, `nSegment`, write counter, and per level `nMerge`/`nSeg`/
  per-segment `{segid, pgnoFirst, pgnoLast}` (`fts5_index.c:88-117`). C structs
  `Fts5Structure`/`Fts5StructureLevel`/`Fts5StructureSegment`
  (`fts5_index.c:402-426`). This is VFS's batch metadata + active-block structure
  in one record.

- **Levels and growth.** `FTS5_MAX_LEVEL 64` (`fts5_index.c:57`). A flush of the
  in-memory hash always writes a **level-0 segment** (`fts5FlushOneHash`,
  `fts5_index.c:5595`; appended then `fts5StructurePromote(p, 0, pStruct)` at
  `fts5_index.c:5791`). A merge reads all segments at level `iLvl` and writes one
  at `iLvl+1` (`fts5IndexMergeLevel`, `fts5_index.c:4763`; output to
  `aLevel[iLvl+1]`). The growth factor is **not a fixed 16x or 64x constant** as
  VFS's prose implies — it is *emergent* from merge fan-in
  (`nAutomerge`/`nUsermerge`/`nCrisisMerge`, see Sec.2) plus a size-based
  promotion heuristic (`fts5StructurePromote`, `fts5_index.c:1536-1580`) that
  promotes a freshly-written segment up or down a level when its leaf-page size
  is out of order relative to neighbours. VFS's "~16x/~64x growth" should be
  stated as *fan-in driven*, not a literal ratio.

- **Flush trigger (in-memory staging bound).** FTS5's in-memory hash is bounded
  by `nHashSize`, default `FTS5_DEFAULT_HASHSIZE (1024*1024)` = **1 MB**
  (`fts5_config.c:23`, set at `fts5_config.c:1063`). Pending bytes tracked in
  `Fts5Index.nPendingData` (`fts5_index.c:355`), flushed by `fts5IndexFlush`
  (`fts5_index.c:5805`). FTS5 bounds staging by **bytes (1 MB)**, not by time —
  the concrete analog of VFS's "frequent small flush bounds staging size." Note
  this flush happens synchronously inside the write when the bound is hit.

### 2. Merge machinery and the crisismerge stall (VFS's headline caveat)

Exact constants, all from `fts5_config.c`:

| Constant | Macro | Default | Range | Meaning |
|---|---|---:|---|---|
| automerge | `FTS5_DEFAULT_AUTOMERGE` | **4** | 0-64 | min segments on a level before incremental auto-merge folds them; 0 disables (`fts5_config.c:20,952-961`) |
| usermerge | `FTS5_DEFAULT_USERMERGE` | **4** | 2-16 | min segments the `'merge'` command folds (`fts5_config.c:21,965-973`) |
| crisismerge | `FTS5_DEFAULT_CRISISMERGE` | **16** | >1, capped `FTS5_MAX_SEGMENT-1` | segments-per-level threshold forcing a **synchronous** merge (`fts5_config.c:22,977-987`) |
| page size | `FTS5_DEFAULT_PAGE_SIZE` | **4050** | 32 .. `FTS5_MAX_PAGE_SIZE`=64 KB | target leaf-page byte size (`fts5_config.c:19,28,928-936`) |
| delete-automerge | `FTS5_DEFAULT_DELETE_AUTOMERGE` | **10** (percent) | — | tombstone-% on a level that triggers a delete-driven merge in `contentless_delete=1` (`fts5_config.c:25,995-998`) |

- **automerge** is incremental and amortized. After a flush,
  `fts5IndexAutomerge` (`fts5_index.c:5020-5039`) computes a *budget* of leaf
  pages proportional to how many `FTS5_WORK_UNIT` (= **64** leaf pages,
  `fts5_index.c:47`) boundaries the write crossed, times `nLevel`
  (`nRem = nWorkUnit * nWork * nLevel`, line 5035), then calls `fts5IndexMerge`
  with `nMin = nAutomerge` (4). Normal merging does a *bounded slice of work per
  write* — exactly the "amortized, localized" property VFS claims.

- **crisismerge is the synchronous stall, and VFS's caveat is accurate.**
  `fts5IndexCrisismerge` (`fts5_index.c:5041-5057`) runs immediately after
  automerge in the same flush and **loops with no page budget**
  (`fts5IndexMergeLevel(p, &pStruct, iLvl, 0)` — the `0` is "no `pnRem` cap")
  while any level has `nSeg >= nCrisisMerge` (16). Both calls sit inline in
  `fts5FlushOneHash` at `fts5_index.c:5796-5797`, driven synchronously from the
  writing statement. Confirmed: once a level accumulates 16 segments, the write
  that pushes it over does a full unbudgeted merge of that level (cascading
  upward via the `while` loop + `fts5StructurePromote`) on the write's critical
  path. VFS's spec language is correct in mechanism. Refinement: the *threshold
  is 16 segments/level* (crisismerge), *normal merge fan-in is 4* (automerge),
  *budget unit is 64 leaf pages* (`FTS5_WORK_UNIT`).

- **usermerge / `merge` command.** `sqlite3Fts5IndexMerge` (`fts5_index.c:5930`)
  implements `INSERT INTO t(t) VALUES('merge', N)`: N work-units with
  `nMin = nUsermerge` (4); negative N triggers an optimize-style full merge with
  `nMin = 1`. The operator-driven background-compaction lever — analog of VFS's
  "periodic large compaction (nightly)".

- **optimize.** `sqlite3Fts5IndexOptimize` (`fts5_index.c:5894`) flushes, then
  merges every level down to a **single segment**, in `FTS5_OPT_WORK_UNIT` =
  **1000**-leaf-page slices (`fts5_index.c:46,5915`). Analog of VFS's full
  reindex (though FTS5 doesn't renumber rowids — it just collapses segments).

### 3. Doclist / posting format and compression

FTS5's on-disk posting format validates VFS's delta+varint plan almost exactly.
From the format comment block at `fts5_index.c:126-203`:

- **Rowid delta-encoding.** A doclist is `varint: first rowid` then
  `zero-or-more { varint: rowid delta (always > 0); poslist }`
  (`fts5_index.c:144-151`). Rowids are sorted and gap-encoded as varints —
  **identical to VFS's "sorted int doc IDs -> delta (gap) encode -> varint."**
  Direct external precedent for VFS's v1 `encoding`.

- **Term prefix-compression on leaf pages.** Each subsequent term is stored as
  `varint: bytes in common with previous term`, `varint: new bytes`, then the new
  bytes (`fts5_index.c:137-142`). VFS has no analog because it keys by a fixed
  24-bit `gram_key`, not variable-length terms — so front-coding does not apply
  and VFS should *not* adopt it. (VFS's packed-int gram key is strictly simpler,
  a deliberate win.)

- **Page size as the block-size analog.** FTS5's leaf pages target `pgsz` = 4050
  bytes (`fts5_config.c:19`), capped at 64 KB (`FTS5_MAX_PAGE_SIZE`,
  `fts5_config.c:28`). VFS's "block of N doc IDs (1,024 / 4,096 / 8,192)" is the
  same idea in *entries* rather than *bytes*. FTS5's **byte budget** is worth
  borrowing: a fixed doc-id count makes a hot gram's block much larger than a
  rare gram's, while a byte budget keeps decode cost uniform. VFS could bound a
  block by "N doc IDs *or* a target compressed byte size, whichever first."

- **Doclist index (skip structure).** For long doclists FTS5 builds a b-tree
  doclist index of `{first-rowid-on-page}` deltas (`fts5_index.c:205-232`), only
  when a doclist spans `FTS5_MIN_DLIDX_SIZE` = **4** or more termless pages
  (`fts5_index.c:49,4258-4260`). Precedent for VFS's `min_doc_id`/`max_doc_id`
  block-skip; VFS's lighter per-block min/max is sufficient.

### 4. Deletes: tombstone, legacy delete-marker, secure-delete

FTS5 has two delete strategies; VFS's "delete-delta + reconcile at compaction"
matches the legacy one closely.

- **Legacy delete = a posting carrying a delete flag (a tombstone in the
  doclist).** A poslist size field is `nSize*2 + bDel` — the low bit is the
  delete flag (`fts5GetPoslistSize`, `fts5_index.c:1857-1863`; `bDel` read at
  `fts5_index.c:1899,2401`). A delete is written as a **new posting in a new
  level-0 segment**, not by editing the old segment. This is exactly VFS's
  append-only delete delta (`action = delete` staged as a new row, never patching
  an existing posting block).

- **Reconcile happens at merge ("key annihilation").** In `fts5IndexMergeLevel`
  the merge skips a record when `pSegIter->nPos==0 && (bOldest || bDel==0)`
  (`fts5_index.c:4850-4851`): a delete marker cancels the matching insert, and
  once data reaches the *oldest* segment the tombstone itself is dropped (nothing
  older can exist to be deleted). This is precisely VFS's "compaction decodes the
  block, drops the deleted doc_id, re-encodes, retires the old block." The worked
  `def -> drop 20` example in spec.md is mechanically the same as FTS5's
  annihilation-at-merge.

- **secure-delete** (`bSecureDelete`, `fts5Int.h:262`; `fts5_config.c:1019-1027`)
  is the opposite trade: instead of leaving a tombstone until merge, it rewrites
  affected leaf page(s) immediately to physically remove old posting bytes (the
  `bSecureDelete` branches in `fts5FlushOneHash`,
  `fts5_index.c:5611,5640-5666,5724`). It exists for privacy (don't leave deleted
  text recoverable), at higher write cost. **VFS does not need it** — VFS blocks
  hold integer doc_ids, not source bytes, so there is no plaintext to scrub; the
  deleted source-content lifecycle is `vfs_entries`'s concern. VFS deliberately
  uses the cheap tombstone-until-compaction path (FTS5 default `bSecureDelete=0`).

- **contentless_delete tombstones + delete-automerge.** For
  `contentless_delete=1` tables FTS5 keeps separate tombstone hash pages per
  segment (`fts5_index.c:234-299`, `nPgTombstone`/`nEntryTombstone` at
  `fts5_index.c:410-412`) and triggers a merge when a level's tombstone ratio
  exceeds `nDeleteMerge` (default **10%**, `fts5IndexFindDeleteMerge`,
  `fts5_index.c:4925-4957`). A strong, directly-citable default for VFS's
  compaction policy: "compact a gram's blocks when stale (deleted) doc_ids exceed
  ~10% of live entries" — proven, better than VFS's current "benchmarked knob."

### 5. Trigram tokenizer — the most important divergence

`fts5_tokenize.c:1275-1421` (`fts5TriCreate` / `fts5TriTokenize`). Three
substantive differences from VFS's tokenizer, two VFS should call out:

- **FTS5 trigrams are per-CHARACTER (UTF-8 codepoint), not per-BYTE.** The
  tokenizer fills `aBuf[]` with **3 decoded codepoints** via `READ_UTF8`
  (`fts5_tokenize.c:1369-1377`) and slides forward **one codepoint at a time**
  (`FTS5_SKIP_UTF8`, `memmove`, append next code — `fts5_tokenize.c:1406-1417`).
  VFS slides over **raw UTF-8 bytes**, so a 3-byte non-ASCII codepoint becomes
  byte-trigrams FTS5 would never emit. **These two indexes are not
  interchangeable** for non-ASCII content. This is the single biggest reason VFS
  cannot simply reuse SQLite's native FTS5 trigram table as the SQLite backend's
  read path and expect identical candidate semantics. (Pure-ASCII code coincides:
  1 byte = 1 codepoint.)

- **Case folding is simple per-codepoint fold, no NFC normalization.** `bFold`
  defaults to 1 (`fts5_tokenize.c:1310`); folding calls
  `sqlite3Fts5UnicodeFold(iCode, iFoldParam)` per codepoint
  (`fts5_tokenize.c:1374,1399`). There is **no NFC normalization** — FTS5 does
  not canonicalize `cafe(NFC)` vs `cafe(NFD)`. VFS *does* NFC-normalize before
  folding (spec sec.Normalization). **VFS is stricter/more correct here**, and
  this is a second reason native FTS5 trigram is not a drop-in for VFS's
  canonical grams. `remove_diacritics` is an optional FTS5 mode
  (`fts5_tokenize.c:1321-1325`) VFS deliberately does not want (it would lose
  information code search needs).

- **Diacritic codepoints are skipped, producing trigrams that span them.** The
  `do { } while(iCode==0)` loops (`fts5_tokenize.c:1370-1375,1392-1400`) skip any
  codepoint folding to 0 (combining marks under `remove_diacritics`), so FTS5 can
  emit a trigram of three non-adjacent source characters. VFS has no equivalent
  and should not — it preserves every byte.

- **The <3-char limitation and the verify step (validates VFS's Cox model).**
  `sqlite3Fts5ExprPattern` (`fts5_expr.c:364-430`) turns a LIKE/GLOB into a
  trigram MATCH: it splits the pattern at wildcard chars and emits a quoted
  phrase **only for runs of >=3 characters** (`fts5ExprCountChar(...)>=3`,
  `fts5_expr.c:394`), AND-combining runs. A pattern with no 3-char literal run
  yields **no MATCH expression** (`*pp = 0`, `fts5_expr.c:424`) -> full scan.
  Exactly VFS's planner contract (fixed-string -> AND of trigrams; no required
  gram -> `GramAny` fallback). The candidate set is then rechecked by the real
  LIKE/GLOB against the **stored column value** — which is why FTS5 cannot do
  LIKE/GLOB acceleration on a contentless table (no value to recheck;
  `fts5IsContentless`, `fts5_main.c:338-342`). **This directly validates VFS's
  mandatory Python verify step and keeping chunk content fetchable** (a fully
  contentless gram index can narrow but cannot self-verify).

---

## Confirms / Contradicts

### Confirms (VFS matches proven FTS5 mechanics)

1. **Append-only flush -> immutable segments/blocks, never in-place mutation.**
   FTS5 writes a new level-0 segment per flush (`fts5_index.c:5791`); merges
   produce new segments. VFS's "writes append to staging, never to blocks; blocks
   are retired, not mutated" is the same model.
2. **Delete-as-tombstone, reconciled at merge.** FTS5's delete-flag posting + key
   annihilation (`fts5_index.c:1863,4850-4851`) is VFS's delete-delta +
   re-encode-at-compaction. The `def`-drop-20 worked example is correct.
3. **delta+varint over sorted integer ids.** `fts5_index.c:144-151` is VFS's
   exact v1 encoding. Integer-rowid keying corroborates VFS's `doc_id` decision.
4. **The crisismerge synchronous-stall caveat is real and accurately described.**
   `fts5IndexCrisismerge` runs unbudgeted, inline, in the write path
   (`fts5_index.c:5041-5057,5797`).
5. **Block-skipping via per-block min/max.** FTS5's doclist-index
   (`fts5_index.c:205-232`) is the heavier version of VFS's
   `min_doc_id`/`max_doc_id`; VFS's lighter scheme is adequate.
6. **Filter -> candidate -> verify against stored content.**
   `sqlite3Fts5ExprPattern` + LIKE/GLOB recheck (`fts5_expr.c:364-430`) is VFS's
   exact Cox model; contentless-can't-recheck validates keeping content.

### Contradicts / should be corrected or sharpened

1. **"~16x or ~64x growth factor" is imprecise.** FTS5 has no fixed level-growth
   ratio. `FTS5_MAX_LEVEL`=64 (`fts5_index.c:57`) is a **level cap, not a growth
   factor**; per-merge fan-in is `nAutomerge`=4 / `nCrisisMerge`=16
   (`fts5_config.c:20-22`). VFS should describe tiering as "merge fan-in F (FTS5
   uses 4), crisis threshold C (FTS5 uses 16)", not as 16x/64x.
2. **VFS's flush/staging bound should name a unit.** FTS5 bounds staging by
   **bytes** (1 MB, `fts5_config.c:23`), not a timer. VFS says "flush (minutes)";
   a byte/row-count bound is more robust under bursty writes —
   "flush on max(staging rows, N) OR T minutes."
3. **Anchor the compaction trigger to a proven default.** FTS5's delete-driven
   compaction fires at **10% tombstones/level** (`fts5_config.c:25`). VFS should
   adopt this as the starting default for "compact when stale doc_ids exceed X%."
4. **Block size is doc-count only; FTS5 uses a byte budget.** Add a
   compressed-byte ceiling option per block (FTS5 `pgsz`=4050) so hot grams don't
   produce one enormous block.
5. **research.md slightly overstates native-FTS5 reuse.** research.md says
   `tokenize='trigram case_sensitive 1'` is "a native code-search-ish option."
   True, but it is **codepoint-trigram + no NFC** — not the same gram alphabet as
   VFS's byte-trigram + NFC for non-ASCII content. Flag that native FTS5 trigram
   is a *different index*, usable as an independent SQLite read accelerator but
   **not** producing VFS's canonical grams.

---

## Proposed edits (not applied)

### spec.md — sec."Durable Storage Model -> Compaction and merge policy"

Replace:
> SQLite FTS5's `crisismerge` and GIN pending-list flushes both produce
> multi-hundred-ms-to-multi-second spikes when a write triggers a large merge
> inline.

with (verified constants):
> SQLite FTS5 makes this concrete. It bounds in-memory staging at 1 MB
> (`FTS5_DEFAULT_HASHSIZE`, `fts5_config.c:23`) and does *incremental*, budgeted
> merging once a level holds `automerge`=4 segments (`FTS5_DEFAULT_AUTOMERGE`,
> `fts5_config.c:20`), in 64-leaf-page work units (`FTS5_WORK_UNIT`,
> `fts5_index.c:47`). But when a level reaches `crisismerge`=16 segments
> (`FTS5_DEFAULT_CRISISMERGE`, `fts5_config.c:22`), the write that crosses the
> threshold performs an **unbudgeted, synchronous** merge of that level inline
> (`fts5IndexCrisismerge`, `fts5_index.c:5041-5057`, called from the flush at
> `fts5_index.c:5797`) — the multi-hundred-ms-to-second spike. VFS therefore keeps
> flush and compaction background/scheduled and never inline with a write
> transaction.

Add, replacing the bare "benchmarked knobs" line:
> Starting defaults, grounded in FTS5's proven values: merge fan-in **4**
> blocks/gram before a tier merge (FTS5 `automerge`); trigger a background
> compaction of a gram when its active block count exceeds **~16** (FTS5
> `crisismerge`, but run it in the background, not inline) or when stale
> (deleted) doc_ids exceed **~10%** of the gram's live doc_ids
> (`FTS5_DEFAULT_DELETE_AUTOMERGE`, `fts5_config.c:25`); bound each block by **N
> doc IDs *or* a target compressed byte size** (FTS5 targets a 4050-byte leaf
> page, `pgsz`, `fts5_config.c:19`). Tune by benchmark; not invariants.

### spec.md — sec."Why blocks, not a single mutable posting list"

Add:
> This is exactly FTS5's design: it never patches an existing segment; a flush
> writes a new level-0 segment and deletes are appended as delete-flagged
> postings, reconciled only when segments are merged ("key annihilation",
> `fts5_index.c:4850-4851`).

### spec.md — Native/Portable Backend Matrix (SQLite row)

Replace with:
> SQLite | FTS5 trigram tokenizer (**codepoint**-trigram + case-fold, no NFC) |
> Produce the portable code-gram index. Native FTS5 trigram is a *different* gram
> alphabet (per-codepoint, no NFC — `fts5_tokenize.c:1369-1417`) and is **not** a
> drop-in for VFS's canonical byte-trigram+NFC stream for non-ASCII content; it
> remains an optional, independent SQLite read accelerator (query path, out of
> scope here).

### spec.md Acceptance Criteria / research.md sec."SQLite FTS5 Trigram Tokenizer"

Add:
> Note: VFS grams are **raw UTF-8 byte** trigrams; SQLite FTS5's native trigram
> tokenizer is **per-codepoint** and applies case-fold but not NFC
> (`fts5_tokenize.c:1369-1417`). The two indexes coincide for pure-ASCII content
> but diverge for any multi-byte codepoint, so the SQLite backend must produce
> VFS's own grams rather than reuse FTS5's.

### spec.md — sec."Deletes and edits as deltas" (after the worked example)

Add:
> VFS uses the cheap tombstone-until-compaction path (FTS5's default,
> `bSecureDelete=0`). FTS5's `secure-delete` option physically scrubs deleted
> *text* from leaf pages for privacy (`fts5_index.c:5611+`); VFS blocks hold only
> integer doc_ids, so there is no plaintext to scrub — deleted source-content
> lifecycle belongs to `vfs_entries`, not the gram index.

### spec.md §6 Phasing (Target) / §7 Rationale — posting-block storage compaction defaults

> - background, copy-on-write compaction; default triggers (FTS5-grounded,
>   tunable): merge fan-in 4 blocks/gram; compact a gram at ~16 active blocks or
>   ~10% stale doc_ids; block bound = N doc IDs or a target compressed byte size.
>   Run all off the write path (FTS5's `crisismerge` is the inline-stall
>   anti-pattern this avoids — `fts5_index.c:5041-5057`).

### spec.md §2 Non-Goals (SQLite read-path note) — reusing FTS5 as the SQLite read path

> Out-of-scope note for the future SQLite query path: FTS5's
> `sqlite3Fts5ExprPattern` (`fts5_expr.c:364-430`) shows the proven shape — break
> the pattern at wildcards, require runs of >=3 chars, AND them, then recheck the
> real LIKE/GLOB against the stored value. VFS's planner already mirrors this; the
> recheck-needs-the-value constraint (FTS5 can't accelerate LIKE/GLOB on a
> contentless table) is why VFS keeps `vfs_entries` content for the Python verify.
> Reusing the *native* FTS5 trigram table as that read path is viable only as a
> separate, ASCII-equivalent accelerator — not as a source of VFS's canonical
> grams (codepoint-vs-byte + NFC divergence above).

---

## Top findings (summary)

1. **Crisismerge caveat is accurate, now with exact constants.** automerge=4,
   crisismerge=16 segments/level, work unit=64 leaf pages, in-memory staging=1 MB
   (`fts5_config.c:19-23`, `fts5_index.c:47`). The unbudgeted inline merge at
   `fts5IndexCrisismerge` (`fts5_index.c:5041-5057`, called inline at
   `fts5_index.c:5797`) is the stall VFS rightly designs around.
2. **VFS's append-only-delta + delete-tombstone + re-encode-at-compaction model
   is FTS5's exact design** (`fts5_index.c:1863,4850-4851,5791`).
3. **delta+varint over sorted integer rowids is FTS5's literal posting format**
   (`fts5_index.c:144-151`) — precedent for VFS's v1 encoding and the integer
   `doc_id` decision.
4. **Borrow FTS5's concrete thresholds** instead of "benchmarked knobs": ~10%
   stale-entry compaction trigger (`fts5_config.c:25`), fan-in 4, crisis-at-16,
   byte-budgeted block size (`pgsz`=4050).
5. **Biggest divergence/correction:** FTS5 trigram is **per-codepoint + case
   fold, no NFC**; VFS is **raw-byte + NFC + casefold**. Not the same index for
   non-ASCII content — SQLite backend must produce VFS's own grams; native FTS5
   trigram is only an optional ASCII-equivalent read accelerator. research.md
   should soften its "native code-search-ish option" line.
6. **Contentless-can't-recheck-LIKE/GLOB validates VFS's mandatory Python
   verify** against stored content (`fts5_expr.c:364-430` + contentless
   constraint).
