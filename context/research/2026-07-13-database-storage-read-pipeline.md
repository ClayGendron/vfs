# 072 research — read pipeline: resolution, projection, listing, consistency, from source

> **Note (2026-07-16 reorg):** this memo moved here from
> `specs/072-database-storage-backend/research-read-pipeline.md`. Sibling citations resolve
> in this directory: `research.md` → `2026-07-13-database-storage-backend.md` ·
> `research-grep-index.md` → `2026-07-13-database-storage-grep-index.md` ·
> `research-pipelines-brief.md` → `2026-07-13-database-storage-pipelines-brief.md` ·
> `research-read-pipeline.md` → `2026-07-13-database-storage-read-pipeline.md` ·
> `research-write-pipeline.md` → `2026-07-13-database-storage-write-pipeline.md` ·
> `research-posting-storage.md` → `2026-07-14-database-storage-posting-storage.md`


- **Date:** 2026-07-13
- **Status:** verified — 2026-07-13; Phase 3 refutation pass applied
  (18 claims: 17 confirmed, 0 miscited-fixed, 1 extrapolation-flagged,
  0 refuted-cut)
- **Method:** the `research.md` / `research-grep-index.md` protocol —
  nine parallel researchers over local checkouts (linux-vfs,
  linux-journal, plan9, unix-history, sqlite, postgres, git, the
  prior-roster re-reader, literature), each grading every question
  **S / C / N / no-precedent** with file:line (or paper §) citations,
  instructed adversarially, extrapolations flagged. This doc is the
  read-pipeline half of the two-doc deliverable
  (`research-pipelines-brief.md`); `research-write-pipeline.md` covers
  W1–W8.
- **Questions under evaluation** (brief inventory, read half):
  - R1 — path resolution (the (c) walk, dcache lessons, resolution
    caches)
  - R2 — stat and projection push-down (`statx` masks → `columns`)
  - R3 — directory listing: order and pagination (gaps #2/#3)
  - R4 — read consistency (snapshot scope, read-your-writes)
  - R5 — version and meta reads (chain reconstruction, corruption)
  - R6 — in-process caching discipline
  - R7 — subtree enumeration at scale (LIKE vs recursive CTE)
  - R8 — error precedence along the read path (the §12 matrix)

## Bottom line

R8 lands the deliverable this doc exists for: a concrete
error-precedence matrix grounded in two independent kernels
(`fs/namei.c`, FreeBSD `vfs_cache_lookup`) that agree once their
frames are aligned — precedence is **positional** (leftmost path
boundary wins, no lookahead), wrong-kind on a node beats permission on
that same node, and the leaf order is **verb-class-dependent**
(create: exists > permission, hand-engineered; delete: permission >
wrong-kind; open/read: existence > kind > permission). V7's
access-clobbers-ENOTDIR bug is the on-record cost of leaving
precedence to statement order. R2 maps `statx` onto the `columns`
projection exactly — validity signaled by an explicit result mask,
never by value — with one direction to pin: statx's mask is a demand
*floor* (cheap fields over-returned), and vfs should choose the strict,
testable variant. The sharpest contradiction is R4: per-op snapshot
isolation is free on SQLite but **not** at Postgres's default READ
COMMITTED, where every statement gets a fresh snapshot — the backend
must pin REPEATABLE READ per op-session or the contract is a lie on
one engine. R3 resolves to record-not-build: v1 keeps materialized
lists; the recorded cursor is a keyset (last name under DDL-pinned
binary collation), because thirty years of NFS cookie archaeology and
JuiceFS's shipped fetcher both say positional cursors are silently
wrong under mutation. R6 converges from three directions (9P, dcache,
AgentFS) on no correctness-bearing in-process state, now with named
admission criteria for any future cache. R5 upgrades hash-verify into
a classified corruption kind (corrupt ≠ missing, per git) and finds
snapshots double as corruption firewalls. R7 stays a spike. R1
confirms the (c) substrate all the way back to V7 — ID-keyed nodes
with name-edges is the original filesystem design, not a database-ism.

## Verdict matrix

S = supports · C = contradicts · N = nuanced · — = no precedent / not
assessed. "prior" = the prior-roster re-reader (juicefs/agentfs/
libsqlfs et al. via `research.md`).

| Question | l-vfs | l-jrnl | plan9 | unix | sqlite | pg | git | prior | lit |
|---|---|---|---|---|---|---|---|---|---|
| R1 resolution | S | — | — | S | — | — | — | S | — |
| R2 projection | S | — | — | — | — | — | — | S | — |
| R3 listing/pagination | — | — | N | — | — | — | — | S | S |
| R4 read consistency | — | — | S | — | S | N | — | N | — |
| R5 version reads | — | — | — | — | — | — | S | —¹ | — |
| R6 caching | — | — | S | — | — | — | — | S | — |
| R7 subtree enumeration | — | — | — | — | — | — | — | N | — |
| R8 error precedence | S | — | — | S | — | — | — | — | — |

¹ prior-roster graded R5 no-precedent: no repo in the nine-repo roster
reads history back at all — itself a load-bearing finding (§R5).

## R1 — path resolution: settled

The (c) substrate is confirmed at its origin, and the resolution-cache
question gets hard admission criteria instead of a vibe.

- **V7 is the original option-(c) system.** "A directory entry is 16
  bytes — an inode number plus a 14-char name — i.e. a pure (name →
  id) edge row; file identity is the inode number; and namei resolves
  a path by per-component walk... No path string is ever stored or
  keyed anywhere in the kernel" (unix-history,
  `unix-history-repo/usr/sys/h/dir.h:1-8; usr/sys/sys/nami.c:153-163,
  192`). Full-path keying has no precedent anywhere in the Unix
  lineage. `node_id` ULID ≙ inode number, `edges`/`parent_id` ≙
  `struct direct`, and the materialized path column ≙ the cache layer
  the kernel had to build anyway (flagged extrapolation, but the
  mapping is one-to-one).
- **Resolution intent is per-verb, and resolve-to-parent is original
  design.** V7 namei threads the operation (lookup/create/delete)
  through resolution; for create it returns the locked *parent* with
  the free slot precomputed — "missing leaf under create" is a
  success-shaped outcome at the resolution layer, not an error
  (`unix-history-repo/usr/sys/sys/nami.c:16-19, 111-126, 173-177`).
  This is the authority for the §12 resolve-to-parent contract: a
  missing leaf with a valid parent classifies differently from a
  missing/wrong-kind ancestor, for every mutating verb.
- **The dcache is the expensive, hazard-bearing half — and it is only
  safe under two conditions vfs cannot meet.** It is strictly
  write-through under heavy locking (every rename updates the cache
  under `rename_lock`, both parents' `i_rwsem`, and
  `s_vfs_rename_mutex` before the change is visible —
  `linux/fs/dcache.c:2869-2963 (esp. 2875-2878),
  linux/fs/dcache.c:85-87`), **and even then every cache hit is
  revalidated**: `lookup_fast` calls `d_revalidate` on the found
  dentry in both RCU and ref-walk modes, invalidating and falling
  through to slow lookup on failure (`linux/fs/namei.c:1838-1885
  (d_revalidate at 1863, 1876; d_invalidate at 1880)`).
  (Flagged extrapolation: `d_revalidate` is an opt-in hook —
  `namei.c:1026-1033` returns 1 immediately unless the fs sets
  `DCACHE_OP_REVALIDATE`, set by NFS/FUSE/overlayfs, not local
  filesystems — so cache-hit-then-trust *is* the kernel's default;
  revalidate-per-hit is the remote-backed-store model, which is the
  applicable one for vfs.)
  `DatabaseStorage` is never the database's sole writer (two
  processes, one DB), so the write-through premise cannot hold for any
  in-process path→row cache; a future cache needs a `d_revalidate`
  analogue — a revision recheck on every hit (linux-vfs, flagged
  extrapolation).
- **Negative caching is a managed liability, not a free win.** Linux
  deliberately caches not-found (unlink converts the dentry to a
  negative entry rather than dropping it, `linux/fs/dcache.c:2496-2537`),
  and later had to add a sysctl (`fs.dentry-negative`) to optionally
  drop-on-delete because unbounded negative caching became a problem.
  Lockless lookup can produce false negatives under concurrent rename
  and needs a locked authority behind it
  (`linux/fs/dcache.c:2319-2331, 2387-2399`). RCU-walk itself is
  optimistic-validate-retry — seqcounts checked after every step, any
  doubt restarts the *entire* walk in locked mode
  (`linux/fs/namei.c:1848-1861, 2135-2148, 2692-2694`) — not lock-free
  trust.
- **FreeBSD kept the same architecture for 45 years** and added
  exactly the two layers the walk demands: a namecache with negative
  entries and a lockless fast path, both wrapped in substantial
  invalidation machinery (`freebsd-src/sys/kern/vfs_cache.c:1338,
  5366-5392`). The prior roster's standing scar (AgentFS's
  hand-invalidated dentry cache) and JuiceFS's `doRepair`
  verify/repair budget stand as the binding amendments from
  `research.md` §1.

**Resolution:** the (c) walk with a transactional (same-store,
same-transaction) path cache is the design; **no in-process resolution
cache in v1**, and not-found results are never cached in-process
(negative-dentry caching is only sound under write-through coherence a
multi-process DB backend cannot have). §10 gains the admission
criteria a future cache must meet (see R6); §12 gains a probe:
create-after-failed-lookup from a second backend instance must succeed
and be visible.

## R2 — stat and projection push-down: settled, one direction to pin

`statx` is the shipped per-field projection precedent, and it maps
onto the `columns` contract cleanly — with the mask, not the value, as
the loud not-loaded signal.

- **The result mask is the authoritative populated signal.** "The
  caller sets bits for wanted fields, and the returned stx_mask
  (result_mask) is the authoritative record of what was actually
  populated — an unsupported field has its bit CLEARED and a
  fabricated value installed, so validity is signaled by mask, never
  by value" (linux-vfs, `linux/include/uapi/linux/stat.h:62-98;
  linux/fs/stat.c:187-188`). This is exactly the projected-out ≠ null
  rule pyfilesystem2's `MissingInfoNamespace` already pinned at the
  Observation layer (`research.md` §3): the harness must assert
  projected-out is distinguishable from null **via the mask**, not by
  value sniffing.
- **The mask is a demand floor, not a hard projection.** Fields
  "available in approximate form without any effort" are filled in
  anyway with the bit set, and `generic_fillattr` unconditionally
  fills mode/size/uid/gid/atime regardless of request_mask — only
  expensive fields are gated
  (`linux/include/uapi/linux/stat.h:88-92; linux/fs/stat.c:82-113`).
  vfs's `columns` projection is *stricter* than the precedent; the
  precedent's non-negotiable part is the explicit result mask. Both
  directions are defensible but only one is testable — **pin the
  strict variant**: the populated set equals the requested set (plus
  the always-on identity fields: path, kind, revision), so the harness
  can assert equality rather than a floor.
- **Cheap-vs-expensive tiers are enforced per-field at the provider
  layer.** ext4 computes btime/DIO/atomic-write geometry only when the
  corresponding bit is set; the VFS fetches the change cookie only if
  requested (`linux/fs/ext4/inode.c:6150,6162,6178;
  linux/fs/stat.c:108-111`). The SQL analogue: the projection is a
  genuine I/O saving, not just wire-bytes — on SQLite a projected-out
  trailing blob's overflow chain is never fetched (write-doc W4
  finding; the physical rationale for content-last column ordering).
- **Reading an expensive field can have write-side costs in the
  precedent — but not in vfs.** Querying the change cookie sets the
  QUERIED flag, forcing the next write to perform a real increment
  (`linux/fs/libfs.c:2048-2071; linux/fs/stat.c:31-62`). vfs stamps
  revision unconditionally per write in the same row-update
  transaction, so revision may be surfaced on **every** Observation
  cheaply — no mask gating needed for it.
- **One divergence to note, not copy:** `STATX_CHANGE_COOKIE` is
  deliberately kernel-only — userspace requests are masked out before
  the fs sees them (`linux/fs/stat.c:706-707, 756-759, 780-783`).
  Linux declined to expose the raw change attribute publicly; vfs's
  constitution (§1.5) mandates the opposite — revision on every Entry
  and Candidate. The divergence is deliberate: vfs's revision has a
  defined public contract (counter semantics, per the write-doc W2
  resolution) where Linux's i_version has only an internal one.

**Resolution:** §3 gains the sentence that every Observation carries
an explicit populated-field mask (the `stx_mask` precedent) as the
loud not-loaded signal; the projection direction is pinned strict
(populated == requested ∪ always-on identity/revision); the harness
asserts by mask, never by value.

## R3 — directory listing, order and pagination: settled (record, not build)

The position: **v1 keeps materialized lists; the recorded protocol
extension is a keyset cursor over the DDL-pinned binary ordering,
never a positional or opaque token.** Three sources triangulate it.

- **The materialized-list cliff is real but not near.** AgentFS —
  the closest peer — materializes the full child list in one `ORDER
  BY name` query with no LIMIT and no cursor, shipped and adequate at
  agent scale (`agentfs/sdk/rust/src/filesystem/agentfs.rs:1741-1768
  (readdir), :1774-1783`). The cliff arrives with recursive verbs over
  large mounts (`research.md` gap #2); the duty now is to record the
  right cursor shape so the extension doesn't get invented under
  pressure.
- **The cursor shape exists, shipped:** JuiceFS's directory fetcher's
  "cursor is the last returned name, the next batch is `WHERE parent
  = ? AND name > ? ORDER BY name LIMIT ?` served by the
  UNIQUE(parent, name) index, with an inline comment pinning the
  invariant: 'need to sorted by name, otherwise the cursor will be
  invalid'" (prior-roster, `juicefs/pkg/meta/sql.go:6079-6110 (keyset
  at 6100-6106, comment at 6110), :65-71`). Ordering is binary by
  construction — the name column is `varbinary(255)`, so `ORDER BY
  name` is byte order on every engine — the destination SeaweedFS
  reached only via a COLLATE "C" retrofit (gap #3). Offset-based entry
  survives only as a compatibility fallback.
- **The negative precedents are unambiguous.** NFSv2's positional
  cookies: "If two READDIRs were separated by one or more operations
  that changed the directory in some way... it was possible that the
  second READDIR could miss entries, or process entries more than
  once... the client would be unaware that any problem existed" (RFC
  1813 §3.3.16, IMPLEMENTATION) — the entire cookieverf apparatus
  exists to convert that silent wrongness into a detectable error, and
  NFSv4.1 still layers SHOULDs amounting to "be a key, not an offset"
  (RFC 5661 §18.23.3, §18.23.4). A cursor that *is* the ordering key
  makes the whole verifier apparatus unnecessary — which is why binary
  collation in DDL is a **pagination-correctness prerequisite**, not
  an ordering nicety (literature, flagged extrapolation). 9P is the
  other negative: its directory cursor is per-fid connection state
  ("seeking other than to the beginning is illegal in a directory",
  `plan9/sys/man/5/read`; fossil ignores the wire offset except 0,
  `plan9/sys/src/cmd/fossil/9dir.c:92-131`) — connection-state cursors
  are unavailable to a stateless protocol, so the NFS-cookie family,
  not 9P, is the recorded shape.
- **Stability semantics are declared, not solved.** JuiceFS runs each
  batch in a fresh read-only transaction — deliberately not one
  snapshot across batches; keyset guarantees no duplicates and no
  skips of already-returned names, while entries inserted/removed
  behind the cursor come and go (`juicefs/pkg/meta/sql.go:6081`). NFS
  never promised more. If pagination lands, declare exactly this as a
  trait (per-batch snapshot, keyset continuity) and pin it in the
  harness under concurrent mutation.

**Resolution:** settled. v1: materialized lists, `ORDER BY` the
binary-collated name column pinned in DDL, identical order asserted
across engines in the harness (gap #3 promoted to correctness
prerequisite). Recorded extension (gap #2): cursor = (last name,
limit) keyset served by the same unique index that arbitrates creates;
declared per-batch-snapshot stability; never OFFSET, never opaque
positional tokens.

## R4 — read consistency: settled-with-amendments

The contract to state: **each protocol method observes a single
committed snapshot fixed at the method's first database read;
sequential methods on one backend observe all previously committed
methods (read-your-writes); no consistency is promised across methods
beyond that.** Free on SQLite; **requires a deliberate isolation
choice on Postgres** — the one real contradiction in this question.

- **SQLite: both halves are substrate-guaranteed.** The read snapshot
  is established when the b-tree read transaction opens —
  `pagerBeginReadTransaction` "essentially makes a snapshot of the
  database at the current point in time and preserves that snapshot
  for use by the reader in spite of concurrent changes"
  (`sqlite/src/pager.c:3238-3252`), mechanism = the recorded mxFrame
  (`sqlite/src/wal.c:100-116`). Read-your-writes across ops holds even
  across pooled connections: the committing connection publishes the
  wal-index header *before* the commit call returns, so any read
  transaction started afterwards snapshots at or after that commit
  (`sqlite/src/wal.c:4243-4256`). Nuance worth pinning: the snapshot
  is per-first-read, not per-BEGIN — `BEGIN DEFERRED` emits no
  transaction opcode at all (`sqlite/src/build.c:5263-5291`) — so a
  read op's consistency point is its first query.
- **Postgres: the contradiction.** "Under READ COMMITTED every call to
  GetTransactionSnapshot falls through to a fresh GetSnapshotData per
  statement; under REPEATABLE READ/SERIALIZABLE the first query's
  snapshot is copied, registered, and returned unchanged"
  (`postgres/src/backend/utils/time/snapmgr.c:271-346 (per-statement
  fall-through at 337-345)`). At the default isolation a
  multi-statement vfs op gets statement-level snapshots, not an
  op-level one. Visibility itself is never torn — every row a writer
  stamped across every table flips visible atomically at commit
  (`postgres/src/backend/access/heap/heapam_visibility.c:938-1096`) —
  but two statements in one op can see two different committed states.
  **The backend pins REPEATABLE READ on op sessions** (JuiceFS's
  shipped choice: `roTxn` opens read-only REPEATABLE READ per op,
  `juicefs/pkg/meta/sql.go roTxn body`) or must declare the weaker
  statement-level contract; pinning is the recommendation.
- **9P calibrates how little the precedent promised.** The consistency
  granule is declared in-protocol (`iounit` — "the maximum size that
  is guaranteed to be transferred atomically", `plan9/sys/man/5/read`);
  above one message there is no atomicity, and there is no snapshot
  isolation anywhere — read-your-writes held only by synchronous-RPC
  accident plus the cache-off default
  (`plan9/sys/src/9/port/devmnt.c:686-731`). vfs's granule is the
  whole op; the 9P lesson is that the granule belongs on the public
  surface, declared the same way.
- **Operational corollary (SQLite):** a held-open read transaction
  pins the WAL reader mark and blocks checkpoint backfill — the WAL
  grows without bound (`sqlite/src/wal.c:2222-2248`, flagged
  extrapolation). One-session-per-op is an operational invariant, not
  just a structural one: never hold sessions, open cursors, or
  unconsumed result iterators across ops; the pressure harness should
  assert WAL size returns to baseline after an op storm.
- **Retry discipline covers reads too** (W7 spillover): JuiceFS's
  retry loop wraps read transactions with the same classifier as
  writes — SQLITE_BUSY and serialization failures hit readers as well
  (`juicefs/pkg/meta/sql.go roTxn body (sql.TxOptions{ReadOnly,
  LevelRepeatableRead}, maxRetry 50)`). The §10 retryable-error
  classifier must wrap read sessions, not only writes. Read-path
  SQLITE_BUSY is rare and genuinely transient (returned only during
  WAL recovery by another process, `sqlite/src/wal.c:2956-2972`).

**Resolution:** settled with two amendments — (a) the per-op snapshot
contract is stated per-dialect with its mechanism (SQLite: first-read
snapshot / BEGIN IMMEDIATE at op start for writes; Postgres:
REPEATABLE READ pinned per op-session, else declare statement-level);
(b) read-your-writes across sequential ops is promised deliberately
for a single backend on a single primary (each op's transaction begins
after the prior op's commit) and is void for replica reads unless
`remote_apply`-class semantics are declared.

## R5 — version and meta reads: settled-with-amendments

Hash-verify-on-reconstruction is confirmed as the shipped norm; what
the spec lacks is the **classification** and the **blast-radius**
story. Reconstruction *latency* stays with the spike.

- **Corrupt is distinct from missing — a classification, not a
  message.** Git marks a failed object bad in a per-pack bad-object
  list, reports "packed object %s (stored in %s) is corrupt" rather
  than not-found, and on a corrupt delta base attempts recovery from
  another copy (`git/packfile.c:983 (mark_bad_packed_object),
  1637-1663; git/odb.c:607-614`). Integrity on read is full-content
  hash verification at the parse layer — `parse_object` re-hashes
  reconstructed content against the OID and fails on mismatch
  (`git/object.c:379-385`). vfs has no second replica to recover from;
  the transferable lesson is the split: **hash mismatch on
  reconstruction classifies as a dedicated corruption kind — never
  not_found, never conflict — naming the version and chain position
  that failed.**
- **Snapshots are corruption firewalls, independently of cost.** A
  corrupt diff row poisons every reconstruction after it only until
  the next snapshot, so SNAPSHOT_INTERVAL=10 caps a single bad row's
  blast radius to at most 9 versions (git researcher, flagged
  extrapolation over `vfs/src/vfs/models/versioning.py:23, 119-140`).
  This is a second, integrity-based justification for the periodic
  snapshot to record wherever the interval is tuned.
- **The cost model is linear-in-chain and git bounds it twice:** a
  depth cap (default 50 — "making it too deep affects the performance
  on the unpacker side, because delta data needs to be applied that
  many times", `git/builtin/pack-objects.c:227-229;
  Documentation/config/pack.adoc:5-8`) plus a 96MiB decompressed-base
  LRU read cache (`git/packfile.c:1516-1633, 1167-1310`). vfs's worst
  case is ≤9 applications, 5× tighter than git's default tolerance —
  the open spike question narrows to Python diff-apply throughput, not
  chain shape.
- **The prior roster has zero precedent for reading history back** —
  JuiceFS restore is a whole-file rename with no content read, AgentFS
  lists versioning as unimplemented, libsqlfs overwrites in place
  (`juicefs/cmd/restore.go:65-151; agentfs/SPEC.md:480`). The
  no-precedent grade is itself the finding: the corruption
  classification must be *pinned in §9*, because nothing upstream will
  supply it.
- **Meta-path version addressing has a filesystem precedent:**
  fossil exposes snapshots in the namespace at
  `/snapshot/yyyy/mmdd/hhmm` and `/archive/yyyy/mmdd`, read through
  the same verb vocabulary with no special version API
  (`plan9/sys/src/cmd/fossil/fs.c:227-229,402,501-582`) — direct
  support for the `__meta__` namespace mapping via `paths.py`
  decomposition, and reading any version there is a normal tree walk,
  never a chain replay (the write-doc W3 counterpoint to forward
  diffs; the read side inherits whatever §9 decides).

**Resolution:** settled with amendments — §9's "content-hash
verification on reconstruction" becomes a classified outcome (a
dedicated corruption kind, distinct from not_found and generic
internal errors, payload naming the failing version and chain
position); the firewall note lands beside the snapshot interval; the
harness gains a corrupted-diff-row probe asserting the kind *and* that
versions at or after the next snapshot still reconstruct.
Reconstruction latency vs chain length × snapshot interval: spike.

## R6 — in-process caching discipline: settled

Three independent lineages fail or constrain caches in the same place
— no invalidation event — and converge on the spec's target: **no
correctness-bearing state between ops.** What this research adds is
the named criteria any future cache must meet before admission.

- **The 9P ecosystem's default is zero client caching.** "By default,
  file contents are always retrieved from the server"; caching is
  per-mount opt-in (`plan9/sys/man/1/bind:127-136`). The opt-in cache
  has exactly one validation event — open: the kernel compares stored
  vs fresh qid.vers in `copen` and discards the file's whole cached
  extent list on mismatch (`plan9/sys/src/9/port/cache.c:214-243`);
  between opens the staleness window is unbounded (no server-to-client
  invalidation, no leases). Even this minimal scheme excludes whole
  classes ("directories aren't cacheable and append-only files confuse
  us", `cache.c:220-223`), and invalidation is whole-file, never
  partial. vfs has no open/clunk lifecycle to hang validation on — its
  ops are one-shot — so a 9P-shaped cache would validate per op, which
  costs a revision read per op, i.e. roughly what the cache was meant
  to save (plan9, flagged extrapolation).
- **The dcache says the same from the other side** (R1): safe only
  under write-through coherence vfs cannot have, *plus*
  revalidate-on-every-hit (`linux/fs/dcache.c:2875-2878 +
  linux/fs/namei.c:1863`; flagged extrapolation — opt-in for
  remote-backed filesystems only, see R1). AgentFS's hand-invalidated dentry cache
  (`research.md` §1) and 9P's open-time-validated cache fail
  identically — converging evidence from independent sources.
- **The one legitimate cache class:** even JuiceFS carries small
  write-path caches — the current trash bucket's (name, inode) is
  cached under a mutex for the hour — benign because "staleness
  degrades to an extra lookup/create, never to wrong results"
  (`juicefs/pkg/meta/base.go:3024-3031, 3039-3050`). The criterion is
  **stale ⇒ slower, never wrong.**
- **The revision stamp is the prerequisite for ever caching.** 9P
  could only build cfs and the kernel mount cache because qid.vers
  already existed protocol-wide; coherence depends on servers bumping
  exactly once per write (`plan9/sys/src/9/port/devmnt.c:718-723`).
  Ship the stamp in Pass A even though v1 holds no cache (§5
  cross-link; already doubly mandated by the §6 watermark).

**Resolution:** settled. §10 keeps the no-correctness-bearing-state
target and gains the admission criteria: a future cache must name (a)
its store-owned version stamp (revision), (b) its validation event —
for one-shot ops this means revalidate-per-hit against the store, the
`d_revalidate` analogue, (c) whole-entry invalidation granularity, and
(d) its excluded classes; caches whose staleness can only cost latency
(the JuiceFS criterion) are permitted with justification; not-found
results are never cached.

## R7 — subtree enumeration at scale: deferred-to-spike

The roster contains a scar and a counter-shape, but no head-to-head.

- **The scar (never do this):** libsqlfs's per-directory listing GLOBs
  `path/*` over the whole subtree and filters depth in application
  code — every shallow list pays the full-subtree cost
  (`libsqlfs/sqlfs.c:853-911 (get_dir_children_num: glob +
  strchr(t2,'/') depth filter)`). The settled half: **shallow listing
  never uses path-prefix scans — parent_id equality only.**
- **The counter-shape:** JuiceFS never enumerates by path prefix at
  all — subtree operations walk parent pointers and paths are
  regenerated on demand (`research.md` §1, `base.go:2329-2378`). So
  the roster has a parent-walk precedent and a prefix-scan scar, but
  no measured crossover between sargable LIKE on the path cache and a
  `parent_id` recursive CTE (prior-roster, flagged extrapolation).
- Whatever wins, deep enumeration runs under §6-style runtime budgets
  (candidate/wall-time caps, truncation-flagged results), mirroring
  the doctrine `research-grep-index.md` §2 already set.

**Resolution:** deferred-to-spike, with the exact measurement named:
**subtree enumeration, path-prefix LIKE on the path-cache column vs
`parent_id` recursive CTE, latency at depth × width** (the brief's
expected-spike item 5), on the same corpus tooling as the other
spikes, at shallow/deep × narrow/wide grid points, identifying the
crossover if one exists. Settled independently of the spike: shallow
lists are parent_id-equality only; budgets + truncation flags apply to
both engines' deep paths.

## R8 — error precedence along the read path: settled (the matrix)

Two kernels, one architecture. Linux (`fs/namei.c`) and FreeBSD
(`vfs_cache_lookup` + `vfs_lookup.c`) were read independently and
their ladders **agree once frames are aligned**: Linux checks
component *i*'s kind at the end of iteration *i* — before iteration
*i+1*'s permission check on it (`linux/fs/namei.c:2594-2669 (may_lookup
at 2600; ENOTDIR at 2662-2667)`); FreeBSD's chokepoint runs
parent-not-a-directory before the permission check on that parent
(`freebsd-src/sys/kern/vfs_cache.c:3190-3213`). Same node-level order,
different loop framing. The governing principles, each with two-source
support:

1. **Precedence is positional, not severity-ranked.** The walk
   processes one component per iteration with no lookahead; whichever
   condition triggers at the leftmost path boundary wins. Ancestor
   errors dominate leaf errors structurally, not by comparison logic
   (linux-vfs; unix-history
   `freebsd-src/sys/kern/vfs_lookup.c:1171-1468;
   unix-history-repo/usr/sys/sys/nami.c:89-93, 111-126`).
2. **Wrong-kind on a node beats permission on that same node — and
   everything deeper.** For `file/x`, wrong_kind wins over both
   permission on `file` and the missing `x`
   (`linux/fs/namei.c:2662-2668, 2780-2786, 2818-2820`). V7 got this
   wrong by accident of statement order — `nami.c` set ENOTDIR then
   called `access()`, which unconditionally overwrote it with EACCES
   (`unix-history-repo/usr/sys/sys/nami.c:89-92;
   usr/sys/sys/fio.c:144-173`); FreeBSD fixed it with an early return
   at one chokepoint. **The rationale for a single classification
   chokepoint rather than accumulated error state is on the record.**
3. **Leaf order is verb-class-dependent; document the asymmetry
   rather than forcing one global ranking** (linux-vfs). Creation
   ranks existence above permission — open's EEXIST-over-EROFS is
   hand-engineered ("for an O_EXCL open we want to return EEXIST not
   EROFS", deferred create_error, `linux/fs/namei.c:4450-4473,
   4516-4519`); deletion ranks permission above wrong-kind
   (`linux/fs/namei.c:3680-3721`); open/read checks existence, then
   kind, then permission (`linux/fs/namei.c:4672-4683, 4238-4295`).
4. **Length errors split by scope:** whole-path budget at ingress
   (071's gates), per-component overlong at the component where it
   occurs, after that boundary's parent checks
   (`linux/fs/namei.c:169-170, 258-259;
   linux/fs/ext4/namei.c:1766-1767`) — resolving `research.md` gap #1's
   classification-site question.
5. **Operating under a deleted ancestor classifies not_found** — not
   wrong_kind, not a race error
   (`freebsd-src/sys/ufs/ufs/ufs_lookup.c:219-221`) — the matrix row
   for whichever delete model §9 lands (trash-reparent per the
   write-doc W6 resolution: the trashed subtree is simply absent from
   resolution).

### The matrix — shared descent ladder (all verbs)

Applied per path boundary, left to right; first failure wins; the walk
never looks ahead. Kind names are vfs's classified kinds.

| co-occurring conditions at one boundary | winning kind | evidence |
|---|---|---|
| ancestor missing + anything deeper | `not_found` (at that component) | `linux/fs/namei.c:2111-2112,2140-2141` |
| ancestor wrong kind + anything deeper (missing leaf, permission, exists) | `wrong_kind` (ancestor) | `linux/fs/namei.c:2662-2668`; `freebsd vfs_cache.c:3190-3213` |
| ancestor wrong kind + no permission on that same node | `wrong_kind` | V7 counterexample `nami.c:89-92` + FreeBSD fix `vfs_cache.c:3202-3204` |
| no search permission on ancestor dir + child missing | `permission` (dir precedes child lookup) | `linux/fs/namei.c:2594-2669 (may_lookup at 2600)` |
| overlong component + component missing | length/`invalid` (at that component) | `linux/fs/ext4/namei.c:1766-1767` |
| whole-path over budget + anything | ingress refusal, before any walk | `linux/fs/namei.c:169-170, 258-259` |
| deleted (trashed) ancestor + anything | `not_found` | `freebsd-src/sys/ufs/ufs/ufs_lookup.c:219-221` |

### The matrix — per-verb leaf table

| verb class | co-occurring conditions at the leaf | winning kind | evidence |
|---|---|---|---|
| read/stat/open | leaf missing + dir-required (trailing slash) | `not_found` (existence first) | `linux/fs/namei.c:2780-2786, 2818-2820` |
| read/stat/open | leaf resolved wrong kind + dir-required | `wrong_kind` (after resolution) | same |
| read/stat/open | leaf wrong kind + no permission on leaf | `wrong_kind` (kind precedes permission at leaf) | `linux/fs/namei.c:4238-4295` |
| create family | leaf exists + verb denied/read-only + no permission | `exists` (hand-engineered priority) | `linux/fs/namei.c:3733-3745, 4450-4473, 4516-4519` |
| create family | leaf missing + verb denied (deny_ops analogue) | refusal before `not_found` | `freebsd-src/sys/kern/vfs_lookup.c:1373-1382` |
| delete family | victim missing + anything | `not_found` first | `linux/fs/namei.c:3680-3721` |
| delete family | victim exists + no permission + wrong kind | `permission` before `wrong_kind` | same |
| delete family | victim right kind, permitted, dir not empty | `not_empty` last | same (kind checks precede EBUSY/emptiness) |
| move | source missing + target exists + would-cycle | `not_found` (source first) | `linux/fs/namei.c:3866-3923, 1813-1820` |
| move | source ok + target exists (no-replace) + would-cycle | `exists` before cycle refusal | `linux/fs/namei.c:3896-3909` |
| move | cycle (either direction) + permission | cycle refusal before permission | `linux/fs/namei.c:5944-5961` |
| move | dir over non-dir / non-dir over dir | `wrong_kind` (syscall-layer translation) | `freebsd-src/sys/kern/vfs_syscalls.c:3877-3907` |
| move | source == target (same node) | success no-op | same |

Two pins the precedent leaves to vfs, decided here:

- **Rename-cycle directions collapse to one kind.** Linux
  distinguishes source-ancestor-of-target → EINVAL from
  target-ancestor-of-source → ENOTEMPTY
  (`linux/fs/namei.c:3896-3909`); POSIX leaves it loose. vfs controls
  both sides of the contract: both directions are the same defect
  (the move would create a parent-pointer cycle) and classify to a
  single cycle-refusal kind, with the Linux split recorded as the
  precedent deliberately not copied. Either choice is conformant; an
  unpinned choice is not.
- **The matrix lives in two layers, matching the router/backend
  split:** a shared resolution ladder (the descent table) plus a small
  per-verb leaf translation table — FreeBSD's `kern_renameat`
  rewriting namei's EISDIR into EINVAL is the precedent that per-verb
  translation belongs above shared resolution
  (`freebsd-src/sys/kern/vfs_syscalls.c:3816-3818, 3877-3907`).
  Assert the translation at the router seam so backends never
  hand-order errors per verb; **zero per-engine conditional
  assertions** (the `research.md` §12 corollary stands).

**Resolution:** settled. The two tables above are the §12
error-ordering matrix (harness upgrade #1), grounded in namei on both
kernels; every row is a conformance assertion identical across
`InMemoryStorage` and `DatabaseStorage`.

## Recommended spec deltas (actionable)

1. **§12:** adopt the R8 matrix verbatim — shared descent ladder +
   per-verb leaf table, asserted at the router seam, zero per-engine
   conditionals. Record the V7 access-clobbers-ENOTDIR bug as the
   rationale for a single early-return classification chokepoint.
   Add rows: deleted-ancestor → `not_found`; per-component length at
   the offending component, whole-path budget at ingress (gap #1);
   rename-cycle collapsed to one kind (Linux's EINVAL/ENOTEMPTY split
   recorded as not copied); move leaf order source-missing →
   target-exists → cycle → permission.
2. **§3:** every Observation carries an explicit populated-field mask
   (the `statx` `stx_mask` precedent) as the loud not-loaded signal;
   projection pinned strict (populated == requested ∪ always-on
   identity/revision fields); harness asserts by mask, never value.
   Note revision is surfaced on every Observation unconditionally
   (the QUERIED write-amplification that gates it in Linux does not
   apply — same-transaction stamp).
3. **§10 (read-consistency contract):** state per-op snapshot
   isolation per dialect with its mechanism — SQLite: snapshot at the
   op's first read (writes: BEGIN IMMEDIATE snapshots at op start);
   Postgres: REPEATABLE READ pinned on op sessions (default READ
   COMMITTED silently gives statement-level snapshots). Promise
   read-your-writes across sequential ops on one backend deliberately;
   declare it void for replica reads absent remote-apply semantics.
4. **§10 (operational invariant):** never hold sessions, cursors, or
   unconsumed iterators across ops — an open read transaction pins the
   SQLite WAL reader mark and blocks checkpoint backfill; pressure
   harness asserts WAL returns to baseline after an op storm. The
   retryable-error classifier wraps read transactions as well as
   writes.
5. **§10 (cache admission criteria):** keep the
   no-correctness-bearing-state target; add the four named criteria
   (store-owned stamp, validation event = revalidate-per-hit for
   one-shot ops, whole-entry invalidation, excluded classes), the
   stale-⇒-slower-never-wrong exemption for latency-only caches, and
   the rule that not-found results are never cached in-process. §5
   cross-link: the revision stamp is the prerequisite for any future
   cache.
6. **§9:** reconstruction hash mismatch becomes a dedicated
   corruption kind (distinct from `not_found` and generic internal
   errors), payload naming the failing version and chain position;
   note snapshots bound corruption blast radius to at most
   SNAPSHOT_INTERVAL−1 versions; harness gains the corrupted-diff-row
   probe (kind asserted + post-snapshot versions still reconstruct).
7. **Gaps #2/#3 recording:** binary collation pinned in DDL promoted
   from ordering-consistency to pagination-correctness prerequisite;
   the recorded cursor shape is keyset (last name, limit) over that
   collation, served by the unique (parent, name) index, with declared
   per-batch-snapshot stability — never OFFSET or opaque positional
   tokens (NFS cookie lineage as the cost of the alternative).
8. **§4/059 + §12:** cite V7 as the origin precedent in the identity
   ADR (ID-keyed nodes with name-edges is the original filesystem
   design; full-path keying has no Unix-lineage precedent); pin the
   resolve-to-parent contract in the harness — missing leaf with valid
   parent classifies differently from missing/wrong-kind ancestor for
   every mutating verb.
9. **Read-path enumeration text (§7-adjacent):** shallow listing is
   parent_id-equality only (the libsqlfs full-subtree-scan scar);
   deep enumeration engine chosen by the R7 spike, both candidates
   under §6-style runtime budgets with truncation flags. §12 gains
   the R1 probe: create-after-failed-lookup from a second backend
   instance succeeds and is visible (no negative caching).

## What only the spike can answer

> **Answered 2026-07-13** — see `spike-results-pipelines.md`.
> Headlines: R7 has **no crossover** — path-prefix LIKE on the
> materialized path column beats the recursive CTE at every measured
> size and depth (12× at 84K descendants; deep enumeration = LIKE,
> CTE stays a graph-verb engine), and shallow listing by `parent_id`
> equality beats prefix-scan-and-filter by up to 795×. R5/W3:
> snapshot-every-10 validated — worst-case replay 0.25–5.2 ms across
> 1 KB–256 KB docs; the write-side diff is the costlier half.

- **R7 — subtree enumeration crossover:** path-prefix LIKE on the
  path-cache column vs `parent_id` recursive CTE, latency at depth ×
  width (shallow/deep × narrow/wide grid, 495K-doc corpus tooling);
  identifies the crossover, if any, that picks the deep-enumeration
  engine. (Brief expected-spike item 5.)
- **R5 (shared with W3) — version-chain reconstruction latency** vs
  chain length × snapshot interval: the read-side number is Python
  diff-apply throughput; chain shape (≤9 applications vs git's
  depth-50 tolerance) is already defensible on precedent, so the spike
  validates the constant, not the design.
- Everything else in R1–R8 is resolved on precedent; no other
  read-pipeline question requires measurement.
