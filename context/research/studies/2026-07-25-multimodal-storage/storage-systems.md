# Study: how production storage systems segment metadata from bytes and tier by size

- **Date**: 2026-07-25
- **Feeds**: [multimodal storage and search brief](../../2026-07-25-multimodal-storage-and-search-brief.md),
  storage questions 1 (blob home / keying), 3 (size ceilings and external
  escape hatch), 4 (binary versioning).
- **Subjects**: SeaweedFS (Apache-2.0, verified `~/Git/Repos/seaweedfs/LICENSE`),
  JuiceFS (Apache-2.0, `~/Git/Repos/juicefs/LICENSE`), Apache OpenDAL
  (Apache-2.0, `~/Git/Repos/opendal/LICENSE`), fsspec (BSD-3,
  `~/Git/Repos/filesystem_spec/LICENSE`), pyfilesystem2 (MIT, checked, not
  deeply used — pure API abstraction, no tiering story). All permissive; no
  GPL/AGPL source was opened. Facebook's Haystack design is cited by its
  public paper URL only.

---

## 1. SeaweedFS: the needle/haystack answer to many small files

### The problem it solves

SeaweedFS "started by implementing Facebook's Haystack design paper"
(`seaweedfs/README.md:136`, paper:
http://www.usenix.org/event/osdi10/tech/full_papers/Beaver.pdf) and claims
"O(1), usually just one disk read operation" per file access
(`README.md:131`). The problem Haystack names: storing each small blob as
its own file in a POSIX filesystem charges per-file metadata (inode,
directory entry, several seeks to resolve path → inode → data) that
dwarfs the payload when files are small and numerous. The fix is to
*pack* many blobs into a few large append-only volume files and keep a
tiny in-memory index per blob.

### The shape

- **Needle** = one stored blob inside a volume file: header (cookie, id,
  size), the data, optional name/mime/pairs, CRC32 checksum, appended
  timestamp, padding to 8-byte alignment
  (`seaweedfs/weed/storage/needle/needle.go:25-45`; full binary layout for
  v1/v2/v3 in `weed/storage/needle/README.md`). Needle size is capped at
  4 GB (`needle.go:23`). Note the needle carries its *own* mime and name —
  the byte store is not metadata-free, it duplicates just enough metadata
  to be self-describing for recovery.
- **Index**: an `.idx` file plus an in-memory or LevelDB map from needle
  id → (offset, size). One entry is `NeedleIdSize + OffsetSize + SizeSize`
  = 16 bytes (`weed/storage/types/needle_types.go:61`), which is the whole
  per-blob metadata cost — the point of the design. The `NeedleMapper`
  interface tracks live/deleted counts and sizes as it goes
  (`weed/storage/needle_map.go:24-39`).
- **The metadata/bytes line**: a separate *filer* stores the directory
  tree in a pluggable DB (SQL/KV) as `Entry` rows — attributes, extended
  map, and a list of `FileChunk` references
  (`weed/filer/entry.go:35-50`). A chunk reference is
  `FileId{volume_id, file_key, cookie}` + offset + size + etag
  (`weed/pb/filer.proto:183-207`). So: **DB holds tree + references;
  volume servers hold bytes; the reference is a minted id, not a hash.**

### Size tiering: the inline threshold

The filer has exactly one tiering knob: `-saveToFilerLimit`, "files
smaller than this limit will be saved in filer store"
(`weed/command/filer.go:113`, default 0 — inlining is opt-in). At write
time, if the first chunk's size is under the limit, the bytes go into
`Entry.Content` (a `[]byte` on the metadata row,
`weed/filer/entry.go:46`) and no volume write happens
(`weed/server/filer_server_handlers_write_upload.go:100-108`). Entry size
is computed as max(chunk total, FileSize, len(Content))
(`entry.go:53`) — content and chunks are mutually exclusive in practice
but the accessor is defensive. **Who decides: server deployment config,
one threshold, applied silently per write. Callers never choose the
tier.**

### Consistency and GC

- **Write ordering**: bytes land on volume servers first; the filer entry
  (with chunk references) commits after. The failure mode is therefore
  *orphaned bytes*, never dangling references from a committed entry.
  `volume.fsck` documents this: "A newly uploaded chunk may appear as
  orphan if metadata commit is still pending"
  (`weed/shell/command_volume_fsck.go:90`), and its orphan scan defaults
  to a 5-hour cutoff before it will even consider a chunk orphaned
  (`command_volume_fsck.go:112`).
- **Deletion is asynchronous and queued**: deleting a filer entry
  enqueues its chunk fids; a background loop drains the queue in batches
  of up to 100,000 fids (~20 bytes each), with retry backoff 5 min → 6 h
  and a 10-attempt cap, and a whitelist of retryable error patterns
  (`weed/filer/filer_deletion.go:23-51`).
- **Deletes are soft at the volume**: a deleted needle is marked in the
  index; bytes stay until **vacuum**. A volume's `garbageLevel()` is
  deletedSize/contentSize (`weed/storage/volume_vacuum.go:43-58`); the
  master vacuums volumes whose reported garbage ratio exceeds a threshold
  (`weed/topology/topology_vacuum.go:38`), by copy-compacting live
  needles into a new `.dat`+`.idx` pair. Compaction distinguishes
  permanently-unreadable needles (safe to drop) from transient I/O errors
  (abort so an operator notices) (`volume_vacuum.go:23-39`).
- **Repair is a tool, not a promise**: `volume.fsck` finds both orphan
  bytes (purgeable) and *missing* chunks (filer references whose bytes
  are gone) — the latter is reported, not auto-healed
  (`command_volume_fsck.go:255-270`).

### Lesson at many-small-files scale

The whole needle apparatus exists because a *filesystem* is a bad
blob-per-small-file store. A relational database is not: it already packs
rows into pages, already maintains the id → location index, already
compacts. The Haystack lesson for vfs is not "pack blobs into volumes
inside the DB" — it is that the per-blob metadata overhead and the
lookup-index shape are the costs to watch, and the DB already pays them
for you. What the DB does *not* absorb (and SeaweedFS also had to bound):
deletion is deferred + batched, space is reclaimed by threshold-driven
compaction, and every queue/batch has a declared size cap.

---

## 2. JuiceFS: metadata in a real DB, bytes in an object store

### The shape

JuiceFS splits exactly along the line the brief hypothesizes: **all
metadata in a transactional DB** (Redis, any SQL engine via xorm, TiKV),
**all file bytes in an object store**. The SQL schema
(`juicefs/pkg/meta/sql.go`) is a close cousin of vfs's rows:

- `node` — inode attrs, narrow row (`sql.go:73-91`).
- `edge` — (parent, name) → inode, the directory tree (`sql.go:65-71`).
- `chunk` — (inode, index) → encoded slice list, a `blob` column holding
  *references only* (`sql.go:167-172`).
- `sliceRef` — (chunkid, size) → refcount (`sql.go:174-178`).
- `delslices` / `delfile` — deferred-deletion queues (`sql.go:180-183`,
  used at `sql.go:2992`).
- `symlink` — target capped at `varbinary(4096)` (`sql.go:186-189`): the
  only "content" the DB ever holds, and it is byte-capped.

File bytes: a file is split into fixed **64 MB chunks**
(`pkg/chunk/chunk.go` consumers; `chunkSize = 1 << 26`,
`pkg/chunk/cached_store.go:40`); writes produce **slices** within a
chunk (`Slice{Id, Size, Off, Len}`, `pkg/meta/interface.go:326-333`);
slices are uploaded as **blocks** of at most `--block-size` (default
4 MB, `cmd/format.go:154-158`) under object keys
`chunks/{id/1M}/{id/1K}/{id}_{blockIndex}_{blockSize}`
(`cached_store.go:76-78`). **The block is the byte-denominated transfer
unit** — bounded upload/retry/cache granularity regardless of file size,
the same reasoning as the brief's byte-denominated flush chunking.

### Keying: minted ids, not hashes

Slice ids come from a monotonic counter (`meta.NewSlice`,
`pkg/vfs/writer.go:78`), not from content hashes. **JuiceFS does no
content-addressed dedup at all.** Sharing between references arises only
from compaction and clones, and is handled by the explicit `sliceRef`
refcount table — reference counting was adopted only once sharing
existed, not as the default posture.

### Consistency: upload first, commit second, compensate on failure

The write path is explicit about ordering
(`pkg/vfs/writer.go:110-125, 195-216`):

1. `flushData()` uploads the slice's blocks and calls `writer.Finish`.
2. Only then does `meta.Write(...)` commit the `Slice` reference into the
   chunk row.
3. If the meta commit fails (ENOENT/ENOSPC/EDQUOT), a compensating
   `store.Remove(id, length)` deletes the just-uploaded object
   (`writer.go:213-216`).

A committed reference therefore always points at existing bytes; the
only steady-state inconsistency is **leaked objects** (upload succeeded,
commit never happened — e.g. crash between 1 and 2). Those are found by
`juicefs gc`, which "scans all objects in data storage and slices in
metadata, comparing them to see if there is any leaked object"
(`cmd/gc.go:43-56`) — offline reconciliation, with `--delete` to act.

### GC: deferred queues + hourly scans, composed with trash

- Deleted files go to the `delfile` queue; an hourly background job
  deletes their data, only touching files deleted more than an hour ago,
  yielding after 50 minutes (`pkg/meta/base.go:1001-1034`).
- `cleanupSlices` runs hourly and deletes any `sliceRef` with
  `refs <= 0` plus its objects (`base.go:1037-1066`; SQL scan is
  literally `WHERE refs <= 0`, `sql.go:3706-3724`). **The refcount is
  advisory-fast, but reclamation is a periodic sweep** — decrement and
  physical delete are decoupled.
- **Trash composes by delaying, not blocking**: with `--trash-days`
  (default 1, `cmd/format.go:194-198`), overwritten/compacted slices go
  to `delslices` with a timestamp and are only reclaimed by
  `cleanupDelayedSlices` after the retention window
  (`base.go:3258-3307`). Trash is a stay of execution inserted between
  dereference and GC — exactly the seam vfs's trash → restore → 90-day
  sweep needs for blobs.
- **Compaction**: many small slices in one chunk get merged into one new
  slice (`doCompactChunk`, `base.go:2868-2895`); the old slices enter the
  delayed-deletion path. Compaction rewrites *references and objects*,
  never diffs content.

---

## 3. OpenDAL: capabilities as the declared shape of a backend

OpenDAL unifies dozens of byte stores behind one `Operator`; the part
relevant here is how it *describes* backend differences: a flat
`Capability` struct of booleans and numeric limits per backend
(`opendal/core/core/src/types/capability.rs:63-136`). Three fields are
the direct precedent for the brief's size-ceiling question:

- `write_multi_max_size` — "AWS S3 supports up to 5GiB per part"
  (`capability.rs:128-130`);
- `write_multi_min_size` — "AWS S3 requires at least 5MiB per part"
  (`capability.rs:131-133`);
- `write_total_max_size` — "Cloudflare D1 has a 1MB total size limit"
  (`capability.rs:134-136`).

That last one is a *database* backend declaring a byte ceiling per
object — the same move as a vfs `DialectProfile` field for a per-row
blob cap. The doctrine matches vfs's dialect design exactly: capabilities
are **declared per backend where the abstraction takes no position**, and
callers branch on the declaration rather than probing (compare
`in_list_budget` at `vfs/src/vfs/storage/backends/database/dialects.py:69,87,107,117`).
Capability defaults are conservative (`Default` derive = all-false /
None), mirroring vfs's GENERIC floor.

---

## 4. fsspec: reference-not-bytes and open-by-reference, concretely

### ReferenceFileSystem — the external escape hatch as a filesystem

`ReferenceFileSystem` presents "byte ranges of some other file as a file
system"; its reference dict is
`{path0: bytes_data, path1: (target_url, offset, size)}`
(`filesystem_spec/fsspec/implementations/reference.py:605-618`). Two
facts matter for the brief:

1. **Inline and external tiers coexist per key**: a reference is either
   literal bytes (small things stored inline in the reference set) or a
   `(url, offset, size)` triple resolved lazily. This is the wire shape
   of "reference-not-bytes" with the inline tier beside it.
2. **Dangling references fail lazily, loudly, and with both names**:
   nothing validates targets at mount; a failed fetch raises
   `ReferenceNotReachable`, which carries the reference *and* the target
   it failed to fetch (`reference.py:34-41`). Read-path coalescing is
   byte-budgeted (`max_gap=64_000`, `max_block=256_000_000`,
   `reference.py:635-636`). The lesson: an external-reference tier does
   not promise byte durability — it promises to name what broke.

### CachingFileSystem — materializing by reference

`CachingFileSystem` layers "chunk-wise local storage of remote files"
over any backend, storing sparse blocks locally keyed by URL hash with
expiry (`fsspec/implementations/cached.py:44-63`); `WholeFileCache` and
`SimpleCache` variants materialize entire files (`cached.py:545,791`).
Precedent for a vfs client resolving an `external_id`/resource-link once
and caching the bytes without the storage layer's involvement.

---

## 5. Synthesis: where the line goes, who decides, what breaks

**Where each system draws the metadata/bytes line:**

| System | Metadata home | Bytes home | Reference shape |
|---|---|---|---|
| SeaweedFS | filer DB (tree, attrs, chunk list) | packed volume files | minted `FileId{volume, key, cookie}` + offset/size |
| JuiceFS | SQL/Redis/TiKV rows | object store blocks | minted slice id + size/off/len, encoded list in a blob column |
| fsspec reference | reference dict (JSON) | any URL | `(url, offset, size)` or inline bytes |
| vfs today | entries row | `content` table, same DB | `entry_id` join (`rows.py:370-380`) |

**Size tiering observed:**

| Tier | SeaweedFS | JuiceFS | fsspec |
|---|---|---|---|
| inline in metadata store | `Entry.Content` below `saveToFilerLimit` (default: never) | never (symlink ≤4096B only) | literal bytes in reference dict |
| packed/managed bytes | needles in volumes, ≤4GB each | 4MB blocks in 64MB chunks | — |
| external reference | — | — | `(url, offset, size)` |

In every case **the threshold is deployment configuration decided at
write time by the storage layer, never by the caller per call** — one
knob (`saveToFilerLimit`, `--block-size`), silently applied.

**Consistency doctrine, unanimous:** write bytes first, commit the
reference second, compensate or GC the orphans. Committed references
never dangle by construction; orphaned bytes are the accepted failure
mode, reclaimed by offline reconciliation (`juicefs gc`, `volume.fsck`)
with generous time cutoffs so in-flight writes are not mistaken for
garbage. Deletion is everywhere deferred: queue → retention window →
batched physical delete → threshold-triggered compaction.

---

## 6. Bearing on the brief's storage questions

### Q1 — entry-keyed vs hash-keyed blob home

Neither production system content-addresses its blobs. Both mint ids and
key bytes by owner (inode/chunk), accepting duplicate bytes; JuiceFS
adds a refcount table only where sharing actually arises (compaction),
and even then reclaims via periodic `refs <= 0` sweeps, not inline
zero-crossing deletes (`sql.go:3706-3724`). The pattern that composes
with vfs's sweep verb is precisely JuiceFS's: **dereference enqueues
(delslices + timestamp), trash-days delays, a background sweep
reclaims** — vfs's 90-day sweep is already the reclamation phase; a
hash-keyed blob table would need only a "last reference swept" check at
sweep time (mark-and-sweep within the sweep transaction) rather than an
online refcount column that every version write contends on. Entry-keyed
duplicates bytes across versions; hash-keyed makes GC a sweep-time join.
The prior art says: dedup is a *choice about version economics* (see Q4),
not a storage-correctness requirement — nobody needed it for
correctness.

### Q3 — size ceilings and the external escape hatch

OpenDAL demonstrates the declaration mechanism: numeric per-backend caps
(`write_total_max_size`) beside boolean capabilities, conservative
defaults — a `DialectProfile` byte-cap field is the same species as
`in_list_budget` (`dialects.py:69`). SeaweedFS demonstrates the inline
threshold as a single server-side knob applied at write time. fsspec's
ReferenceFileSystem demonstrates the external tier's contract: inline
bytes and `(url, offset, size)` references coexist per key, resolution
is lazy, and the dangling case is a first-class error naming both the
reference and the target — the right wire behavior for
`Entry.external_id` (`entry.py:82`) projected as `resource_link`.
Precedent supports **declare the ceiling now** (a per-dialect cap plus a
mount-level inline threshold) and **defer the external resolver**: the
escape hatch can be pure reference + typed failure, with fsspec-style
caching layered client-side later.

### Q4 — snapshot-only binary versioning

No system studied diffs binary content — anywhere. Overwrite writes new
slices/needles; the old bytes ride the deferred-deletion path; JuiceFS
compaction merges small slices into bigger ones but never delta-encodes
(`base.go:2868-2895`). SeaweedFS vacuum copy-compacts live needles and
drops dead ones (`volume_vacuum.go:43-58`) — reclamation, not diffing.
Snapshot-only binary versions are the industry answer. This also
resolves the pack question by analogy: JuiceFS compaction operates on
*references and packing*, never on content — vfs `pack` should skip
media bodies (no diffs to build) while remaining free to do
reference-level work if versions become hash references, at which point
unchanged media across versions costs one row, not one blob — the one
genuine argument the prior art offers *for* hash-keying.

### On the sidecar-table hypothesis itself

The Haystack lesson cuts in vfs's favor: needle/volume packing exists to
fix POSIX filesystems' per-small-file cost; a relational DB already
provides packed pages, the id index, and compaction. A blob-per-row
sidecar table keyed by entry (or hash) is not the naive design Haystack
fixed — the actual hazards are the ones vfs's dialect doctrine already
names (packet caps, LOB rules, bind budgets), plus the two disciplines
every system here converged on: **byte-denominated transfer units**
(JuiceFS's 4MB block) and **deferred, batched, threshold-driven
reclamation** (delslices/vacuum) riding the existing trash → sweep
lifecycle.
