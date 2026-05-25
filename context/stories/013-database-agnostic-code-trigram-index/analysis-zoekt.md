# Analysis — Validating the VFS Code-Gram Index against `sourcegraph/zoekt`

Repo studied: `/Users/claygendron/Git/Repos/zoekt` (no edits made there). All
citations are `path:line` into the zoekt repo.

## Findings

### 1. Positional trigrams: how offsets are stored
- Zoekt stores the **rune offset of every ngram occurrence**, not a doc id
  (`doc/design.md:29-37`; "banana" example `:33-36`).
- Offsets are **global rune offsets across the concatenated shard**, not
  per-doc: each trigram recorded at `newOff := endRune + runeIndex - 2`
  (`index/shard_builder.go:214`), `endRune` being the running rune count of
  prior docs (`:183, 249`).
- Each ngram's posting list is a **delta+varint offset stream**:
  `delta := uint64(newOff - pl.lastOff)`, single-byte fast path for
  `delta < 0x80` else `binary.PutUvarint` (`index/shard_builder.go:238-247`).
- Document boundaries recovered separately via `fileEndRunes`
  (`index/indexdata.go:58`; TOC `index/toc.go:81,95`); byte boundaries via
  `boundaries[docID]` (`index/contentprovider.go:50-54`).
- A substring match needs only **2 posting-list intersections** (first + last
  trigram, "at the right distance apart"), length-independent, and can pick the
  **rarest trigram pair** (`doc/design.md:38-39, 56-64`).
- Stated cost: **~3x corpus** on disk = 2x offsets + 1x content
  (`doc/design.md:68-70, 145-146`).

### 2. rune→byte table ("every 100 runes") and uint32 caps
- `ngramSize = 3` (`index/shard_builder.go:39`), `runeOffsetFrequency = 100`
  (`:60`). Byte offset recorded every 100 runes (`:199-201`).
- The table is **sparse-by-correction**: `makeRuneOffsetMap` stores only
  `(runeOffset, byteOffset)` pairs deviating from "1 byte/rune"; pure-ASCII files
  store an empty map and short-circuit (`index/bits.go:356-402`;
  `doc/design.md:106-109`).
- ngram = **three 21-bit runes in a uint64** `b[0]<<42|b[1]<<21|b[2]`
  (`index/bits.go:82-84,99`); ASCII trigrams use a direct-indexed `1<<21` array
  (`index/shard_builder.go:71-78,92`).
- **uint32 offsets** cap a shard at 4 GB / ~1 GB content
  (`doc/design.md:148-151`) — a direct consequence of positional offsets. VFS
  doc ids have no such pressure.

### 3. Operational limits (the hot-gram/skip mitigations VFS leaves unpinned)
Defaults in `SetDefaults` (`index/builder.go:312-333`):

| Limit | Default | Site |
|---|---|---|
| Max file size `SizeMax` | **2 MiB** (`2<<20`) | `index/builder.go:325-326` |
| Max shard size `ShardMax` | **100 MiB** | `:328-329` |
| Max distinct trigrams/doc `TrigramMax` | **20,000** | `:331-332`, field doc `:75-76` |

Enforced in `DocChecker.Check` (`index/shard_builder.go:680-721`), called from
`Builder.Add` (`index/builder.go:616-625`). Order: (1) too-large → drop content
from memory (`:617-622, 636-641`); (2) `< 3 bytes` → too-small
(`shard_builder.go:685-687`); (3) **any NUL byte → binary** (`:689-691`, entire
heuristic); (4) distinct-trigram count > cap → too-many (`:699-718`), with a
cheap upper-bound short-circuit `len(content)-2 <= cap` skipping the walk
(`:693-697`). Allowlist escape hatch via `IgnoreSizeMax`
(`builder.go:616, 695`). Feature-version history confirms the size default was
deliberately bumped (`index/toc.go:42`).

### 4. Shard/segment architecture → maps to VFS posting blocks + compaction
- One mmap-able shard file per repo with a TOC of sections (`fileContents`,
  `postings`, `ngramText`, `runeOffsets`, `fileEndRunes`, `branchMasks`,
  `metaData`, …) (`index/toc.go:71-104`; `doc/design.md:131-146`).
- **Format versioning** (`IndexFormatVersion`/`FeatureVersion`/`WriteMin`/
  `ReadMin`, `index/toc.go:31-66`) = the role of VFS's per-block `encoding`
  field: evolve format without migrating old data.
- **Immutable + copy-on-write merge**: `Merge` concatenates shards into a
  **compound shard** by re-emitting every live doc
  (`index/merge.go:19-51, 92-140, 271-308`); `Explode` is the inverse
  (`:145-269`). Never in-place edit.
- **Tombstones**: `SetTombstone`/`UnsetTombstone` flip a flag in a `.meta` JSON
  sidecar (`index/tombstones.go:15-54`); merge/explode skip tombstoned repos
  (`merge.go:36-38, 108-111, 233-235`); space reclaimed lazily at next merge. =
  VFS's "stage delete, retire blocks at compaction," one granularity coarser.

### 5. Branch masks (multi-version without duplication)
- Each blob carries a `uint64` branch bitmask (`index/shard_builder.go:298`; TOC
  `index/toc.go:88`; 64-bit since v12 `:28`). Identical content across N branches
  stored **once** with OR'd bits (`doc/design.md:114-127`); expanded back to
  names at read (`merge.go:296-306`). Relevant to VFS file versions/snapshots
  (see E).

### 6. Content ngram selection & varint encoding
- Indexes **every** content trigram up to the 20k cap; selectivity is a
  *query*-time concern (rare-pair pick, `doc/design.md:62-64`). Matches VFS
  "store every gram" (Open Q3).
- Encoding is **delta+uvarint** throughout (`shard_builder.go:238-247`;
  `bits.go:245-283`; doc-sections `:193-231`). Format v6 even removed the posting
  size prefix (`toc.go:22`). **No zstd/Roaring layer** — plain delta+varint over
  mmap suffices at Android/Chrome scale, validating VFS's "start simple
  (delta-varint)."

### 7. Case handling
- Zoekt indexes **original case** and expands the *query* to all case variants
  via `unicode.SimpleFold` (`index/bits.go:26-47`; `doc/design.md:92-98`) —
  inverse of VFS's fold-the-index choice.

## Confirms / Contradicts
- **A. Immutable segments + CoW merge + tombstones — CONFIRMS strongly.** VFS's
  staging→flush→immutable blocks→CoW-compaction is zoekt's model one granularity
  finer (`merge.go`, `tombstones.go`).
- **B. delta+varint + evolvable format — CONFIRMS.** Zoekt's lack of a heavier
  codec validates "start simple."
- **C. store-every-gram, selective-at-query — CONFIRMS** (`doc/design.md:62-64`;
  VFS Open Q3).
- **D. Case strategy — DIVERGES; VFS's single folded stream is the better fit.**
  Zoekt expands the *query* (cheap because positional touches only ~2 lists);
  for a doc-level many-trigram AND, query-side case expansion multiplies the
  candidate set. VFS folding the *index* is the right model choice, not just
  storage saving.
- **E. Branch masks ≈ VFS versions/snapshots — PARTIALLY TRANSFERABLE.** Not a
  current gap (each entry row is its own `doc_id`); the proven escape hatch if
  version explosion ever inflates the index.
- **F. Positional vs doc-level — RECOMMENDATION: keep doc-level, do NOT adopt
  positional.** Positional's win (2-list distance check, rarest-pair) depends on
  **offset arithmetic over an mmap'd byte stream**; VFS intersects integer
  doc-id sets in SQL (SQLite/Postgres/MSSQL) and has **no carrier** for distance
  math — offsets would either explode rows or hide in blobs the DB can't compute
  over, forcing a Python pull that VFS's regex verify already does. Positional
  also costs ~2x storage and the uint32 cap. The one idea worth borrowing —
  rarest-gram-first intersection — is already in VFS's gram-statistics/query plan
  (out of scope).

## Proposed edits (owner applies)

**Edit 1 — Adopt concrete limits (biggest gap).** Add a new spec.md §"Indexing
Limits" after §"Index Correctness Contract":
- Max indexable content size **2 MiB** per file/chunk (zoekt `SizeMax`).
- Max distinct trigrams/doc **20,000** (zoekt `TrigramMax`).
- Binary detection: reject if any NUL byte (zoekt's whole heuristic).
- Too-small: reject `< 3 bytes`.
- Optimization: skip the distinct-trigram walk when `len(content)-2 <= cap`;
  provide an `IgnoreSizeMax`-style allowlist. Cite `index/shard_builder.go:680-721`
  and `index/builder.go:312-333`. Also replace the vague "file skip limits for
  high unique-gram files" in §Risks → Storage growth / Hot grams with these
  numbers.

**Edit 2 — Sharpen positional-vs-doc-level note** (spec.md §Why or new note near
§Durable Storage Model): state zoekt is positional (`doc/design.md:29-64`), its
~2x/uint32-cap cost (`:68-70, 148-151`), and that VFS chooses doc-level because
the optimization **has no carrier in a relational doc-set engine**; the
rarest-first idea lives in the out-of-scope query path.

**Edit 3 — Case divergence** (spec.md §Risks → Case-insensitive candidate
breadth): note zoekt expands the *query* (`index/bits.go:26-47`), cheap only for
~2-list positional; folding the index is the right fit for VFS's many-trigram
AND.

**Edit 4 — Cite zoekt in compaction/delete sections** (spec.md §Compaction and
merge policy / §Deletes as deltas): compound-shard re-emit merge
(`merge.go:92-140, 271-308`) + `.meta` tombstones (`tombstones.go:15-54`) as a
same-shape precedent.

**Edit 5 — Add multi-version dedup** (landed in spec.md §10 Deferred
Options): branch-mask-style version-membership dedup
(`doc/design.md:114-127`, `shard_builder.go:298`) as a future escape hatch, not a
current gap.

**Edit 6 — implementation.md encoding note:** zoekt validates the minimal codec —
plain delta+uvarint over mmap, no zstd/Roaring (`shard_builder.go:238-247`,
`bits.go:245-283`), evolving via format version (`toc.go:31-66`); start
delta-varint, defer Roaring/EF.

## Top findings (the short version)
1. **Concrete limits to adopt:** 2 MiB file cap, 20,000 distinct-trigrams/doc,
   NUL-byte=binary, <3 bytes=too-small — `DocChecker.Check`
   (`index/shard_builder.go:680-721`), defaults `index/builder.go:325-332`. This
   fills VFS's only real spec gap.
2. **Positional is right for zoekt, wrong for VFS** — recommend keeping
   doc-level; positional has no offset-arithmetic carrier in SQL and costs ~2x
   storage + uint32 4GB/1GB cap (`doc/design.md:29-64, 68-70, 148-151`).
3. **Architecture confirmed:** immutable segments + CoW compound-shard merge +
   tombstones + delta+varint + format-version evolvability all match VFS's design
   one granularity finer.
4. **Case strategy diverges**, and VFS's single folded stream is the better fit
   for a many-trigram AND (zoekt expands the query instead, `index/bits.go:26-47`).
5. **Branch masks** are the proven version/snapshot dedup pattern — flag as a
   forward-looking Open Question, not a current gap.

> Note: this file was authored by the zoekt research agent, which was blocked
> from writing directly; content transcribed verbatim from its report.
