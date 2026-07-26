# Study: git's content-addressed object store (public docs only)

- **Date**: 2026-07-25
- **For**: multimodal storage and search brief
  ([../../2026-07-25-multimodal-storage-and-search-brief.md](../../2026-07-25-multimodal-storage-and-search-brief.md)),
  storage questions 1, 4, 5, and lifecycle question 10.
- **License note**: git is GPLv2; per the binding license rule this study
  used **no local clone** — every fact below is sourced from git-scm.com
  documentation, the Pro Git book (CC BY-NC-SA, read online), and the
  GitHub engineering blog, cited by URL.

git is the canonical prior art for the brief's question 1 alternative:
a hash-keyed, content-addressed blob store where dedup falls out of the
key and deletion becomes a garbage-collection problem. This study takes
the system on its own terms — what is addressed, how small objects are
compacted, how binaries delta, how GC composes with a grace window, and
what it cost to change the hash function — then maps each mechanism onto
the vfs blob-table decision.

---

## 1. Content addressing: hash of a *typed, sized* payload

Git is "a content-addressable filesystem … a simple key-value data
store": insert any content, receive a key derived from the content
itself ([Pro Git ch. 10.2](https://git-scm.com/book/en/v2/Git-Internals-Git-Objects)).
The key is **not** the hash of the raw bytes. Git prepends a header —
`"<type> <size>\0"` (e.g. `blob 16\0`) — and hashes header+content:

```
store = "blob #{content.bytesize}\0" + content
sha1  = SHA1(store)          # the object's name
disk  = zlib_deflate(store)  # what is written
```

([Pro Git ch. 10.2](https://git-scm.com/book/en/v2/Git-Internals-Git-Objects),
which walks the exact Ruby reimplementation and shows it matching
`git hash-object --stdin`.)

Three design facts follow:

- **The type is inside the address.** A blob and a tree with identical
  bytes have different names; the store is namespaced by type at the
  hash level, and `git cat-file -t` can always recover the type from
  the payload alone. The object is self-describing.
- **The size is inside the address.** The header's byte count is a free
  integrity check on inflation — a truncated object cannot silently
  parse.
- **Dedup is not a feature, it is arithmetic.** Identical content
  produces the identical key regardless of filename, directory, branch,
  or how many trees point at it. Pro Git demonstrates two versions of
  `test.txt` producing two objects — and any number of files with the
  same content producing one
  ([Pro Git ch. 10.2](https://git-scm.com/book/en/v2/Git-Internals-Git-Objects)).

Storage layout for loose objects: `.git/objects/<first-2-hex>/<remaining-38>`
— a 256-way fan-out so no single directory accumulates every object
([Pro Git ch. 10.2](https://git-scm.com/book/en/v2/Git-Internals-Git-Objects)).
This is a filesystem workaround (directory scans degrade); a database
B-tree keyed on the hash needs no equivalent.

**vfs mapping (brief Q1, Q5).** vfs already stamps `content_hash`
(sha256 hex, `String(64)`) on every version
(`src/vfs/models/rows.py:388`), so the *address* half of a
content-addressed blob table exists. Git's typed-payload choice poses a
real question: should vfs hash raw bytes, or `mime + size + bytes`?
Git's reason for in-band type — the store holds four structurally
different kinds and must self-describe — does not apply to a
single-kind blob table. Hashing **raw bytes only** keeps dedup across
mime relabels (the same PNG uploaded as `image/png` and
`application/octet-stream` stores once) and keeps mime an out-of-band
column owned by the entry/version, mutable without rewriting bytes.
The size-in-header integrity trick translates directly as a
`size_bytes` column checked on read.

## 2. Loose objects vs packfiles: the small-object problem

Every write initially lands as one zlib-compressed file per object.
Two consequences at scale, both documented:

- **Full-copy versions.** Change one line in a 22K file and git stores
  a second, complete 22K object; Pro Git shows two ~7K-compressed
  near-duplicates on disk
  ([Pro Git ch. 10.4](https://git-scm.com/book/en/v2/Git-Internals-Packfiles)).
- **File-count explosion.** GitHub (18.6 PB of git data) reports that
  storing many objects as individual files "can lead to performance
  problems, including exhausting your system's available inodes"
  ([GitHub blog, Scaling Git's garbage collection](https://github.blog/engineering/architecture-optimization/scaling-gits-garbage-collection/)).

The compaction answer is the **packfile**: many objects concatenated
into one file, each entry individually compressed and optionally
delta-encoded, with a separate `.idx` (256-entry fan-out table, sorted
names, offsets, CRC32s per object; v2 adds 8-byte offsets for >2 GiB
packs) ([gitformat-pack](https://git-scm.com/docs/gitformat-pack)).
Packing triggers when loose objects exceed `gc.auto` (default **6700**),
when packs exceed `gc.autoPackLimit` (50), on push, or on manual `gc`
([git-gc](https://git-scm.com/docs/git-gc),
[Pro Git ch. 10.4](https://git-scm.com/book/en/v2/Git-Internals-Packfiles)).
Pro Git's toy example: 15K of loose objects → 7K packed.

The deeper pattern: **git writes fast and sloppy, then compacts
offline.** Ingest never pays layout costs; a background batch job
(repack) pays them later, and the index makes the compacted form as
addressable as the loose form.

**vfs mapping (brief Q1, Q2).** The loose-object problem is a
*filesystem* pathology — per-object inodes, per-directory scans, 4K
block rounding. A database blob table gets git's packfile properties
for free: rows share pages, the primary-key B-tree *is* the pack index
with fan-out, and the engine's storage manager (TOAST, off-row
varbinary(max), LOB segments) is the pack. The part worth porting is
not the format but the **write-fast/compact-later posture**: bulk
ingest should append blobs with the cheapest possible statement shape
(chunked by byte budget, per the brief's Q2), leaving dedup
arbitration (`ON CONFLICT DO NOTHING`-style) and any compaction to the
engine rather than pre-sorting or pre-deduping 10,000 files in Python
memory.

## 3. Delta compression: binaries *do* delta — until git decides they shouldn't

The pack format defines two deltified representations — `OBJ_OFS_DELTA`
(base named by negative byte offset in the same pack) and
`OBJ_REF_DELTA` (base named by full hash; permits "thin packs") — whose
delta payload is a byte-level instruction stream: *copy offset+length
from base* or *insert literal bytes*
([gitformat-pack](https://git-scm.com/docs/gitformat-pack)). Nothing in
the mechanism is line- or text-aware: the delta payload is a byte-level
copy/insert instruction stream defined identically for all object types
— nothing in gitformat-pack's instruction format conditions it on
content, so its content-type-agnosticism is an inference from the
format, not a sentence the doc states. Repack sorts candidates "by type, size,
and optionally names" and compares each against a sliding `--window`
(default 10) of neighbors, chaining up to `--depth` (default 50); the
**newest version is stored whole and older versions become deltas
against it**, "because you're most likely to need faster access to the
most recent version"
([git-repack](https://git-scm.com/docs/git-repack),
[Pro Git ch. 10.4](https://git-scm.com/book/en/v2/Git-Internals-Packfiles)).

But git then carves out media explicitly:

- `core.bigFileThreshold` (default **512 MiB**): "Files larger than
  this size are stored deflated, without attempting delta compression.
  … Additionally files larger than this size are always treated as
  binary. This should be reasonable for most projects as source code
  and other text files can still be delta compressed, but larger binary
  media files won't be"
  ([git-config](https://git-scm.com/docs/git-config)).
- The `delta` attribute set to false disables delta attempts per path
  ([git-repack](https://git-scm.com/docs/git-repack)).

So git's considered position on "binary has no diff story" is nuanced:
byte-range deltas *work* on binaries and git happily uses them for
small ones, but for large media the memory cost of delta search
outweighs the win — because already-compressed formats (JPEG, MP4, zip)
change most of their bytes under any edit, deltas find little to copy.
Git chooses **deflate-only snapshots** for exactly the content class
the vfs brief is about.

**vfs mapping (brief Q4).** Snapshot-only binary versioning is not a
compromise; it is what git itself converges to for media. The win git's
deltas capture for *text* history is captured for *media* history by
content addressing alone: an unchanged image across ten versions is ten
hash references to one blob row, cost zero — the same "unchanged
content is a pointer" economics, without a delta engine. A
byte-delta layer for large binaries would be re-adding the machinery
git turns off at 512 MiB. Corollary for `pack` (the vfs text-diff
verb): skipping media entries mirrors git's `-delta` attribute, and a
declared per-row size cap (brief Q3) mirrors `core.bigFileThreshold` —
a *configured constant with a documented rationale*, not an emergent
limit.

## 4. GC: reachability walks, not refcounts

git never counts references. Deletion is a two-phase, walk-based
protocol:

1. **Becoming unreachable is free.** Deleting a branch touches one ref
   file; no object is touched. Objects are merely *no longer reachable*.
2. **Pruning is a batch reachability walk.** `git prune` runs
   `fsck --unreachable` from the roots — everything under `refs/`, the
   index, and reflog entries — and removes loose objects the walk never
   reached ([git-prune](https://git-scm.com/docs/git-prune),
   [git-fsck](https://git-scm.com/docs/git-fsck)). fsck distinguishes
   *unreachable* (not reachable from any root) from *dangling* (never
   directly referenced at all); `--lost-found` can rescue either.

### The grace period is the concurrency answer

`git gc` prunes with `--expire 2.weeks.ago` (`gc.pruneExpire`, default
**two weeks**): "Any object with modification time newer than the
`--prune` date is kept, along with everything reachable from it," and
"most operations that add an object to the database update [its]
modification time" — *freshening* — so a just-written object survives
even while unreachable
([git-gc](https://git-scm.com/docs/git-gc)). The rationale is a
documented race: a writer stores objects *first* and only afterwards
creates the ref that makes them reachable, so a concurrent GC can
observe a brand-new object as garbage. The grace window papers over
this; the docs are candid that it is a mitigation, not a proof:
"these features fall short of a complete solution, so users who run
commands concurrently have to live with some risk of corruption (which
seems to be low in practice)" ([git-gc](https://git-scm.com/docs/git-gc)).
`--prune=now` is explicitly flagged as raising corruption risk.

### Cruft packs: the grace period at scale

Expiry needs per-object mtimes, but packed objects share one file
mtime — "rewriting any single unreachable object has the effect of
updating the mtimes of *all* of a repository's unreachable objects,"
making permanent expiry nearly impossible — while exploding unreachable
objects back to loose files melts inodes. Git ≥2.37's answer is the
**cruft pack** (`gc.cruftPacks`, now default true): one pack holding
all unreachable-but-fresh objects plus a `.mtimes` sidecar recording
each object's own timestamp
([git-gc](https://git-scm.com/docs/git-gc),
[gitformat-pack](https://git-scm.com/docs/gitformat-pack),
[GitHub blog](https://github.blog/engineering/architecture-optimization/scaling-gits-garbage-collection/)).
GitHub's numbers: a pathological repository fell from 186 GB to 2 GB;
github/github itself from ~57 GB to ~27 GB.

### Why not refcounting? (reconstructed — no ADR exists)

No git document says "we rejected reference counting"; the design
record instead shows the preconditions refcounting needs are absent,
and honesty requires labeling this section reconstruction:

- **No transactions.** The object store is bare files written
  lock-free; a count would be mutable shared state updated on every
  ref move, reflog append, and index touch, with no atomicity to
  protect it. The store's one concession to locking — the transition
  design's `loose-object-idx.lock` with `O_CREAT | O_EXCL`
  ([hash-function-transition](https://git-scm.com/docs/hash-function-transition))
  — shows how alien mutable shared metadata is here.
- **Objects are written before they are referenced**, so every new
  object's true count is transiently zero at its most vulnerable
  moment — refcounting would GC exactly the wrong objects without the
  same mtime grace period reachability needs anyway.
- **Roots are heterogeneous and half of them aren't edges.**
  "Reachable from the index," "reachable from a reflog entry,"
  "reachable via `objects/info/alternates` from another repository"
  ([git-prune](https://git-scm.com/docs/git-prune)) are predicates,
  not pointer writes; no increment site exists for them.
- **Counts corrupt silently and stay corrupted; walks self-heal.** A
  missed decrement leaks forever; a reachability walk recomputes truth
  from scratch every run.

## 5. The SHA-1 → SHA-256 transition: what rekeying a CAS costs

The transition design
([hash-function-transition](https://git-scm.com/docs/hash-function-transition))
is the definitive record of what it costs to change the key function of
a content-addressed store after the fact. SHAttered (Feb 2017) broke
SHA-1 collision resistance; git picked SHA-256 in 2018. The bill:

- **Every object name changes** — and because trees and commits embed
  the names of the objects they reference, **every object's *content*
  changes too**. Rekeying is not a column migration; it is a rewrite of
  the entire object graph in reverse-topological order (an object
  cannot be converted until everything it references has been).
- **Blobs are the exception**: "Blobs are identical in both formats
  (no references to other objects)" — a blob's SHA-256 name is just a
  rehash; its bytes never change.
- Interop requires **bidirectional translation tables** (a
  `loose-object-idx` mapping file plus pack index v3 carrying *both*
  name tables per pack), dual signatures (`gpgsig` + `gpgsig-sha256`),
  and four user-visible modes (dark launch → early → late →
  post-transition) rolled out over years. A flag-day cutover was
  rejected as infeasible for large ecosystems.

**vfs mapping (brief Q1).** Two lessons, one cheap and one structural:

1. **Record the algorithm now.** `content_hash` is bare sha256 hex
   today (`rows.py:388`). Either a companion algorithm column/prefix
   from day one, or an ADR note that the column is definitionally
   sha256 and a future change is a declared migration — the cost of
   ambiguity is git's "is this 40-digit name SHA-1 or something newer?"
   problem, which forced them to lean on digest *length* for
   disambiguation.
2. **Keep blobs leaves.** git's rekeying pain lived entirely in the
   objects that embed hashes (trees, commits); blobs rehashed for
   free. If vfs blob rows never contain hash references — versions
   point at blobs, blobs point at nothing — then a future rehash is a
   bounded table rebuild plus foreign-key repoint, the *easy* half of
   git's problem. Do not let derived-artifact or chunk rows embed blob
   hashes inside opaque payloads.

## 6. Composing hash-keyed blobs with vfs trash → restore → sweep

Direct translation of git's two-phase deletion onto the vfs lifecycle
(brief Q1 + Q10), given the sweep verb at
`src/vfs/storage/protocol.py:255`:

- **Trash/sweep of an entry = ref deletion.** Blob rows are untouched;
  sweeping version rows merely makes some blobs unreachable. Restore
  before sweep re-links the same hashes at zero byte cost — git's
  reflog-recovery story for free.
- **Blob GC = the reachability walk, as one anti-join.** git's walk
  over refs/index/reflogs collapses, in SQL, to "blob rows with no
  surviving referent in `versions.content_hash`" — a `NOT EXISTS`
  anti-join, batch-chunked under the dialect membership budgets exactly
  like any other bulk statement. It is self-healing (recomputed truth
  each run, like fsck) and needs no bookkeeping on any write path.
  Refcount columns are *available* to vfs in a way they were not to
  git — SQL has the transactions git lacks — but they buy only a
  cheaper GC query at the price of a decrement/increment obligation on
  every write, copy, restore, and sweep path forever, and they still
  corrupt silently on a missed path. Git's walk survives translation;
  git's *reasons* refcounting was impossible mostly do not, which makes
  choosing the walk a judgment call vfs gets to make on simplicity
  grounds rather than necessity.
- **The grace period may collapse into the transaction.** git's
  two-week window exists because objects land before the refs that
  make them reachable, with no atomicity spanning both. If a vfs write
  inserts the blob row and the version row referencing it in **one
  transaction**, a concurrent GC can never observe the git race —
  read-committed visibility hides the blob until its referent exists.
  The residual hazard is dedup arbitration: if "insert blob if absent"
  is a separate committed statement (the natural shape for 10k-batch
  chunked ingest), a blob can briefly exist unreferenced, and a
  `created_at > now() - grace` guard on the GC anti-join — git's
  freshening check, one predicate — closes it. Days, not git's two
  weeks, since the window is one batch's flush latency, not a human
  workflow.
- **Cruft packs do not port; their lesson does.** The cruft mechanism
  solves filesystem mtime granularity, which a `created_at`/
  `last_referenced_at` column simply doesn't have. The durable lesson
  is that *expiry metadata must be per-object and survive compaction* —
  trivially true of a column, catastrophically untrue of a file mtime.

## 7. Answers on the brief's terms

- **Q1 (blob home, keying).** Git demonstrates the hash-keyed shape
  end-to-end: dedup by arithmetic, immutable rows, cheap versions,
  recovery-friendly deletion — at the price of a GC obligation. Its GC
  is genuinely simple in SQL terms (one chunked anti-join under the
  sweep verb, plus a short insert-grace predicate), and its worst
  scaling pathologies (loose-object inodes, pack mtimes) are
  filesystem artifacts a database does not inherit. The strongest
  git-derived argument *for* entry-keyed rows instead would be "no GC
  at all"; the strongest against is that every version rewrite of a
  10 MB asset duplicates 10 MB, which is the loose-object full-copy
  problem git built packfiles to escape.
- **Q4 (binary versioning).** Git's own doctrine for media is
  snapshot + dedup, not delta (`core.bigFileThreshold`, `-delta`).
  Content addressing already delivers the dominant saving (unchanged
  versions are pointers). vfs `pack` skipping media entries mirrors
  git's per-path delta opt-out.
- **Q5 (exclusivity enforcement).** Git's typed-payload addressing is
  the wrong import: vfs blobs are one kind, so hash raw bytes and keep
  mime/kind out-of-band, preserving dedup across relabels.
- **Q10 (lifecycle).** Two-phase deletion (unreference now, collect
  later, grace window against in-flight writers) is the proven
  composition — and vfs's transactional substrate lets it hold the
  invariant git openly cannot: zero corruption risk under concurrency,
  not "low in practice."

## Sources

- Pro Git ch. 10.2, Git Objects — https://git-scm.com/book/en/v2/Git-Internals-Git-Objects
- Pro Git ch. 10.4, Packfiles — https://git-scm.com/book/en/v2/Git-Internals-Packfiles
- gitformat-pack — https://git-scm.com/docs/gitformat-pack
- git-gc — https://git-scm.com/docs/git-gc
- git-prune — https://git-scm.com/docs/git-prune
- git-repack — https://git-scm.com/docs/git-repack
- git-fsck — https://git-scm.com/docs/git-fsck
- hash-function-transition — https://git-scm.com/docs/hash-function-transition
- git-config (`core.bigFileThreshold`) — https://git-scm.com/docs/git-config
- GitHub blog, "Scaling Git's garbage collection" — https://github.blog/engineering/architecture-optimization/scaling-gits-garbage-collection/
- vfs ground truth: `src/vfs/models/rows.py:347,388,410` (content_hash
  columns), `src/vfs/storage/protocol.py:255` (sweep verb).
