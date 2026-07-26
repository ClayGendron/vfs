# Write-vs-topology prior art — six-domain survey synthesis

**Date:** 2026-07-25
**Status:** research memo, feeds spec 086 (guarded-bump write-vs-topology hardening)
**Question:** for each decision §7 of the adversarial campaign report left open —
guard shape, the reverse-ordering window, the residual purge window, copy
coherence, foreign keys, error classification, detection/repair — what does
prior art actually do, and what does it license or warn against?
**Evidence:** empirical ground truth is
`context/research/2026-07-25-write-vs-topology-adversarial-campaign.md`
(§7 decision list). Prior art below is from six survey passes over the
read-only reference checkouts (kernel, SQL-backed filesystems, Jackrabbit
Oak, fsck/GC tooling, VFS abstraction layers, graph/authorization stores).
All citations verified first-hand; described, never copied.

---

## 1. The field's answer to the core race

Create-under-concurrently-relocated-parent — vfs's torn-path-cache race — is a
solved problem three different ways, and the solutions sort by one structural
question: **does the system materialize full paths, or is the parent chain the
only truth?**

**Kernels: lock the parent, serialize topology, never store a path.** Linux
closes every namespace-writer race with exactly two locks: the parent
directory's `i_rwsem` held exclusive per operation (name set stable, so
lookup-miss-then-create is atomic), and one per-filesystem
`s_vfs_rename_mutex` for cross-directory rename (tree topology frozen while
the loop check runs) — `linux/Documentation/filesystems/directory-locking.rst:1-62`,
`linux/fs/namei.c:5895-5918`. The load-bearing invariant comment is explicit:
topology changes only under the mutex *and* the parent of anything being
attached is locked — vfs currently has the first half only. The dead-directory
mechanism is the exact create-under-trashed-parent analog: rmdir (and
rename-over-target, one mechanism) sets a monotonic `S_DEAD` mark inside the
critical section that removes the directory
(`linux/fs/namei.c:5339-5380,6059-6062`), and every attach path checks it under
the same parent lock and fails ENOENT (`linux/fs/namei.c:3734-3741`).
FreeBSD reaches the same end with trylock/drop-all/restart plus **re-resolving
source and target by name after every reacquisition**
(`freebsd-src/sys/ufs/ufs/ufs_vnops.c:1304-1352`) — anything resolved before
you held your serialization is presumed stale and re-derived.

Crucially, the kernel's celebrated optimistic machinery (RCU-walk, seqlocks)
exists **only for readers**. Path assembly walks child-to-root under a
generation check and throws the whole buffer away if any rename happened
anywhere (`linux/fs/d_path.c:140-190`) — staleness-on-return is accepted, a
mixed-epoch path never is. No kernel writer proceeds optimistically against a
concurrent rename. vfs's unserialized write-vs-topology posture goes beyond
anything the kernel does.

**SQL filesystems: store one name per edge; the tear is inexpressible.**
juicefs and agentfs are (parent, name) edge tables with no path column
(`juicefs/pkg/meta/sql.go:65-71`, `agentfs/sdk/go/schema.go:29-36`); directory
rename/trash is one row update, O(1), zero descendants touched
(`juicefs/pkg/meta/sql.go:2232-2246`). libsqlfs and seaweedfs materialize the
path as the *only* identity and pay O(subtree) renames inside one transaction
(`libsqlfs/sqlfs.c:2246-2347`, `seaweedfs/weed/server/filer_grpc_server_rename.go:26-48`).
**No surveyed system stores both a parent pointer and a materialized path on
the same row.** vfs's tear class — `row.path` contradicting the `parent_id`
chain — is only expressible in the dual representation vfs alone has.
juicefs's create-side protection is a rowcount-verified parent UPDATE at
commit (`juicefs/pkg/meta/sql.go:1925-1938`) plus a read-time
parent-already-in-trash check (`:1807-1809`): vfs's headline candidate,
shipped, in production, on vfs's engines.

**Oak: force the parent into every child-add commit; first committer wins.**
Every add-child commit stamps a versioned entry on the parent document (the
commit root lands there — `jackrabbit-oak/.../document/Commit.java:318-332,524-545`),
so add-vs-delete-parent always intersects on one shared document and
first-committer-wins arbitration runs without locks or descendant
re-collection (`Commit.java:589-670`, `Collision.java:71-99`). The loser gets
a typed conflict, suspends until the winner is visible, rebases, retries
(`DocumentNodeStoreBranch.java:168-229`). And Oak *still* leaks orphans across
cluster nodes — its answer was default-on orphan GC
(`VersionGarbageCollector.java:173`) plus a report-only checker, not more
locking. Repair is part of the correctness budget, not a fallback.

The structural observation, made explicit: **the systems that prevent the race
either lock the parent, refuse to materialize paths, or force a shared
arbitration row into both commits. vfs currently does none of the three** —
its path cache is a materialized closure maintained with neither neo4j's lock,
nor ladybug's row versioning, nor SpiceDB's recompute-at-snapshot (see §3.1).
That is why the campaign found what it found.

---

## 2. Per-decision precedent

### 2.1 The guarded bump (§7.1) — precedent is strong and adds two corrections

- juicefs implements it exactly: parent-node UPDATE at commit, 0 affected rows
  = parent removed/relocated, abort (`juicefs/pkg/meta/sql.go:1925-1938`).
  Oak's single-doc fast path commits conditionally on `_modCount`
  (`Commit.java:481-516`) — conditional-update-verified-by-match is the
  universal optimistic primitive. minio's conditional PUT is the same shape
  with a lock instead of a rowcount: take narrow per-object exclusivity,
  re-read, verify, write (`minio/cmd/erasure-object.go:1261-1286`).
- **Engine wrinkle vfs must inherit:** under MySQL REPEATABLE READ a 0-row
  parent update is ambiguous (snapshot staleness vs removed parent), so
  juicefs maps 0 rows to EBUSY-retry-whole-txn on MySQL and ENOENT elsewhere
  (`sql.go:1198-1228`). A naive engine-uniform "0 rows = conflict, fail"
  misbehaves on MySQL RR. This is a per-dialect fact for `DialectProfile`
  territory, and confirms §7.1's "engine-uniform guard" needs an
  engine-*aware* failure interpretation.
- **Guard-skipping is schema-dependent and unavailable to vfs:** juicefs
  deliberately skips the parent bump for file creates in hot directories
  (`SkipDirMtime`, default 100ms, `juicefs/cmd/flags.go:323-327`) — safe only
  because its edge schema makes the worst case a coherent edge on a
  trash-bound inode. With a path cache, any skip reintroduces the tear.
- The kernel translation of the dead-directory pattern (§1) is precisely the
  guarded bump: the guard predicate *is* the S_DEAD check, and the
  transaction's atomic commit *is* the lock scope. Both kernels make the
  losing create fail ENOENT — precedent for classifying the miss as
  `not_found`/`conflict`, never silent success.

### 2.2 Generation tokens (§7.2, "topology generation the write revalidates")

- **Coarse counters are respectable.** Linux uses ONE global seqlock for
  every rename in the kernel (`linux/fs/dcache.c:85`) and eats false retries
  because moves are rare and retry is cheap. FUSE ships a literal per-connection
  "epoch" whose increment lazily invalidates everything older
  (`libfuse/include/fuse_lowlevel.h:1795-1806`). A per-mount generation bumped
  by every topology verb is *coarser* than the sketched per-directory design
  and has the stronger precedent.
- **The discipline is fixed everywhere it appears:** the mover bumps; the
  racing party validates at its commit point; on mismatch it abandons and
  re-executes the whole operation — never patches partial state
  (`linux/fs/dcache.c:2387-2398`, `fs/namei.c:920-945`).
- SpiceDB is the richest living version: a zedtoken is a global revision
  watermark minted at write commit, spent on an explicit staleness dial
  (`spicedb/pkg/middleware/consistency/consistency.go:143-218`), with
  write-side preconditions evaluated inside the commit transaction
  (`spicedb/internal/services/v1/relationships.go:440-446`). But SpiceDB can
  *read at* old revisions only because it rebuilt append-only MVCC on Postgres
  (`created_xid`/`deleted_xid`, `spicedb/internal/datastore/postgres/schema/schema.go:21-22`).
  vfs updates rows in place: it can mirror the freshness *check* (revalidate,
  abort/retry on mismatch) but not read-at-old-generation. openfga, which
  dropped the token for a binary cache-bypass enum
  (`openfga/internal/graph/cached_resolver.go:173-205`), is the cautionary
  degenerate end: without a token you cannot express "fresh relative to MY
  last observation" — which is exactly what write-side revalidation needs.
- **Negative result:** no VFS abstraction layer generation-stamps directory
  state. fsspec's dircache is TTL/LRU/self-write-invalidation only, blind to
  rival mutators (`filesystem_spec/fsspec/dircache.py:27-62`). The counter
  must be argued from vfs's own campaign evidence, not by citation from the
  layer vfs most resembles.

### 2.3 The reverse ordering (§2.1 / §7.2) — stale descendant collection

- FreeBSD's rename is the direct precedent for "re-run `_descendant_rewrites`
  after `_reparent_to_trash`": after every lock reacquisition it re-resolves
  source and target from scratch and panics if a post-lock re-lookup disagrees
  (`freebsd-src/sys/ufs/ufs/ufs_vnops.c:1304-1352,1698-1706`). TerminusDB
  retries by re-executing the entire transaction body against fresh state
  (`terminusdb/src/core/transaction/database.pl:180-264`). Prior art retries
  by *recomputing from fresh state*, never by patching a stale collection.
- Oak closes the same window structurally: delete tombstones each descendant
  document individually, and a descendant added after its snapshot conflicts
  on the shared parent doc rather than being silently missed
  (`CommitBuilder.java:170-188`). That is the generation-token answer to the
  reverse ordering: give the write a stamp on the parent the topology verb
  must conflict with, and the stale-list problem dissolves symmetrically.
- ladybug/kuzu shows the other pole: freeze one snapshot for the whole verb
  (per-row version vectors, `ladybug/src/storage/table/version_info.cpp:147-241`)
  — unavailable to vfs at READ COMMITTED across five engines — or serialize
  writers outright (its default is one write transaction system-wide,
  `src/transaction/transaction_manager.cpp:54-102`). No read-side cleverness
  at READ COMMITTED fixes a stale collection; the fix is re-collect, id-closure,
  or a conflict surface.

### 2.4 The residual purge window (§4) and orphaned content rows (§2.4)

- Oak proves the campaign's structural claim from the other direction: Oak
  *can* mark a collision on an uncommitted rival only because intent is
  published before commit (`Collision.java:32-46`); SQL isolation removes
  exactly that visibility. **No purge-side re-read can close the window** —
  the fix is write-side revalidation, an FK, or a durable pre-transaction
  intent record. Apache AGE ships the same hole knowingly: its vertex-delete
  edge check reads the query snapshot, endpoints have no FKs, and a rival
  edge insert committing after the snapshot creates a permanently dangling
  edge with no engine objection (`age/src/backend/executor/cypher_delete.c:686-716`).
  If vfs declines both the FK and write-side revalidation, it is choosing
  AGE's hole — acceptable only paired with a fenced sweep.
- neo4j gives the minimum sufficient write-side shape: relationship create
  takes **shared** "parent alive" locks on both endpoints and re-asserts node
  existence under the lock; node deletion takes the exclusive form
  (`neo4j/.../RecordStorageLocks.java:128-159`,
  `Operations.java:509-527`). Writers never block writers — the
  shared/exclusive asymmetry preserves vfs's batch-writer throughput doctrine
  far better than a FOR UPDATE subtree lock.
- For the content-row leak, juicefs's durable-intent two-phase delete is the
  recipe: the metadata transaction that unlinks also inserts a `delfile`
  intent row (`juicefs/pkg/meta/sql.go:2062-2080`); background reaping deletes
  chunks in small rowcount-verified transactions and deletes the intent row
  *last* (`sql.go:3781-3801`), with a refs<=0 second-chance sweep
  (`sql.go:3706-3724`). seaweedfs states the ordering rule as an in-code
  comment: data is deletable only after the metadata transaction that stops
  referencing it commits (`seaweedfs/weed/server/filer_grpc_server_rename.go:49-55`).
- Orphan GC grace fences converged independently on vfs's exact mechanism as
  their justification — "content is written before the metadata referencing
  it commits": juicefs skips objects younger than 1h (`juicefs/cmd/gc.go:112-121`),
  Oak refuses candidates newer than the mark phase minus a 24h interval
  (`MarkSweepGarbageCollector.java:453-489`), seaweedfs uses a 5h cutoff
  (`command_volume_fsck.go:87-92`). A fenced orphan-content sweep in vfs's
  existing sweep verb (age fence + run under the per-mount topology
  serialization) is unusually well-precedented, and juicefs models "detached
  topology intermediates" as a separate orphan class with a longer 24h tier
  (`cmd/gc.go:137-146`) — vfs's stranded-live-rows class.

### 2.5 Copy coherence (§2.2)

- minio: copy metadata and body come from ONE handle produced by one locked,
  quorum-verified read (`minio/cmd/object-handlers.go:1269-1305`,
  `cmd/erasure-object.go:203-244`) — the tear is structurally impossible.
  This is the single-SELECT fix (`content_joined()`) in the wild.
- opendal exposes the alternative when two reads are unavoidable: pin the
  second read to the first's observation (`source_version`/`if_match` on the
  copy op, `opendal/core/core/src/raw/ops.rs:869-907`) and surface a mismatch
  as a first-class `ConditionNotMatch` the caller owns
  (`core/core/src/types/error.rs:74-84`). Notably, opendal's own multipart
  copy path contains vfs's exact stat-then-read window unless the caller pins
  the version (`core/services/s3/src/copier.rs:89-108,173-191`) — even the
  best-regarded layer has this bug class where a backend forces two round
  trips. One read where possible; pinned second read where not.

### 2.6 Foreign keys (§7.4)

- **Unanimous zero FKs** across juicefs, libsqlfs, seaweedfs, agentfs
  (`juicefs/pkg/meta/sql.go:65-260`, `agentfs/sdk/go/schema.go:16-47`), and
  the graph stores can't express them (multi-table endpoints —
  `age/src/backend/commands/label_commands.c:552-580`; even
  SERIALIZABLE-pinned gel hand-compiles triggers instead,
  `gel/edb/pgsql/delta.py:6108-6178`).
- But the no-FK position is never taken alone: **every no-FK peer ships a
  repair scan and a leak reaper as the compensating control** — juicefs
  `fsck --repair` (`cmd/fsck.go:37-72`, `pkg/meta/sql.go:4146-4175`) plus gc;
  Oak's checkers plus default-on orphan GC. vfs currently has neither half.
  The divergence from prior art is not the missing FKs; it is the missing
  fsck.

### 2.7 Classification honesty (§2.5)

- opendal: per-service translation seam mapping (status, vendor code) →
  small closed ErrorKind + orthogonal tri-state retryability, every row
  citing vendor docs; raw text survives only as message payload
  (`opendal/core/core/src/types/error.rs:49-151`,
  `core/services/s3/src/core.rs:2040-2127`). Unknowns default to
  Unexpected + non-retryable. Exhausted retries are stamped persistent so
  nothing downstream re-retries (`core/layers/retry/src/lib.rs:331`).
- pyfilesystem2 adds two refinements vfs needs: classification is
  **operation-shaped** — two errno tables because the same errno means
  different things for file vs directory ops
  (`pyfilesystem2/fs/error_tools.py:30-63`) — and the reported path is
  rewritten into the caller's coordinate system at every wrapping boundary
  (`fs/error_tools.py:96-117`). The same driver unique-violation can mean
  `exists` for a create and `conflict` for a lost move arbitration; the verb
  is classification input. Trash-internal addresses must never surface.
- gel translates Postgres 40001 into a typed retryable
  `TransactionSerializationError` at the seam
  (`gel/edb/server/compiler/errormech.py:97`); SpiceDB retries 40001 with
  bounded backoff. juicefs treats duplicate-key as *retryable*: re-run,
  re-probe, return an honest EEXIST from application logic
  (`juicefs/pkg/meta/sql.go:1198-1228`) — a no-SAVEPOINT alternative to the
  §7.2 SAVEPOINT-translation candidate.
- SQLAlchemy will never supply this: it models isolation and
  `insertmanyvalues_max_parameters` but no retryable-error taxonomy at all
  (`sqlalchemy/lib/sqlalchemy/engine/default.py:971-980`). Every production
  peer hand-built the classifier. It is legitimately vfs-declared
  `DialectProfile` knowledge.

### 2.8 Detection and repair (§7.4)

- **What to check:** every mature checker is a two-way reconciliation of a
  derived copy against its source of truth. The exact analog of
  path-vs-parent-chain is Oak's consistency check — resolve each node by
  traversal from the root AND directly, report disagreement either way
  (`jackrabbit-oak/.../document/Consistency.java:47-95`,
  `OrphanedNodeCheck.java:80-107`) — and Postgres amcheck's
  `bt_index_parent_check` (parent/child downlink coherence,
  `postgres/contrib/amcheck/verify_nbtree.c:243-306`).
- **Online false positives, three strategies:** age fence (seaweedfs 5h,
  juicefs skip-pending); lock-tiered invariants — amcheck checks parent/child
  coherence only under a writer-excluding ShareLock, weaker invariants
  lock-free (`verify_nbtree.c:279-306`) — which maps directly onto vfs: cheap
  always-available checks lock-free, the parent-chain recomputation under the
  per-mount topology serialization; or snapshot isolation by construction
  (SQLite, `src/pragma.c:1695-1760`).
- **Repair posture, universal:** detection default and free; repair opt-in;
  destructive repair doubly gated. juicefs auto-repairs only *constructive*
  fixes under an explicit flag + explicit path scope
  (`cmd/fsck.go:56-59`, `pkg/meta/base.go:2621-2642`); seaweedfs labels
  destructive flags "expert only" and revokes the operator's own delete
  authorization mid-run when its knowledge was incomplete
  (`command_volume_fsck.go:259-264`); minio deletes dangling objects only on
  evidence beyond parity with ambiguity as an absolute veto
  (`cmd/erasure-healing.go:986-1055`). Path-cache recomputation from the
  parent chain is constructive (juicefs's nlink-correction class); deleting
  orphaned content rows is destructive and needs its own opt-in.
- **Scheduling:** the explicitly-invoked-verb constraint is well-precedented —
  SQLite's checker is a statement, amcheck is SQL functions, seaweedfs fsck a
  manual heavy command, Oak blob GC an operator-triggered MBean. Caution: any
  deferred-deletion design (tombstone now, reap later) implicitly demands a
  background drainer (juicefs's hourly goroutines,
  `pkg/meta/base.go:807-815`); vfs should keep the full-diff-and-act-within-
  the-invocation shape, folded into the existing sweep verb the way juicefs
  gc folds trash-edge cleanup into one command.
- **Findings as observations:** in SQLite and Postgres the check IS a query
  and findings ARE typed result rows (`verify_heapam.c:917-942`); minio's GET
  that trips over incoherence serves the client AND emits a durable heal-queue
  observation without failing the verb (`cmd/erasure-object.go:395-419`).
  Direct precedent for surfacing orphan probes as sweep-result warnings and
  path-incoherence as observations on normal verbs.

---

## 3. Convergences and divergences

### 3.1 Convergences (multiple independent systems; these carry the weight)

1. **No working system maintains an in-place-updated materialized closure
   without a lock or a version.** neo4j locks the derived structure's inputs
   (the DEGREES lock, whose in-code comment narrates vfs's exact torn-derived-
   value anomaly, `RecordStorageLocks.java:162-175`); ladybug versions the
   derived CSR with the base rows; SpiceDB refuses to materialize and
   recomputes at a named revision. vfs's current design matches none of them.
2. **Conditional-update-verified-by-match is the universal optimistic write
   primitive** (juicefs parent bump, Oak `_modCount`, juicefs chunk delete,
   minio precondition-under-lock). The guarded bump is not novel machinery;
   it is the field's standard part.
3. **Retry means re-derive from fresh state, whole-operation** — never patch
   a stale intermediate (Linux RCU-walk restart, FreeBSD rename relock,
   TerminusDB retry_transaction, Oak rebase). And Oak refines it: suspend
   until the winner is visible so the redrive cannot re-lose to the same
   commit.
4. **Relocation and destruction are one failure mode** — S_DEAD is set by
   rmdir and rename-over-target alike; juicefs's trash-parent check covers
   both. Independently confirms the campaign's §4.3 conclusion.
5. **No FKs, yes fsck** — every no-FK peer compensates with a shipped repair
   scan plus a leak reaper; orphans are an expected operational state with a
   recovery path, and grace-fenced GC is the standard reclaim mechanism, with
   the fence justified everywhere by vfs's own §2.4 mechanism verbatim.
6. **Classify at the seam** — closed taxonomy + retryability axis, raw driver
   text demoted to payload, unknowns conservative (opendal, gel, pyfilesystem2,
   juicefs). Nobody lets driver text reach the public surface as the
   classification.
7. **Success is verified by the presence of the expected observation.** minio
   defines write success and read visibility against the same committed
   metadata and documents the envelope where the guarantee is void; opendal
   distrusts even a 200 OK and re-classifies when the expected ETag is absent
   (`core/services/s3/src/copier.rs:126-137`). vfs's observation-honesty pin
   (`writes.py:289/:698`) is the field's norm, and fsspec's silent skip of
   mid-copy vanishing files (`fsspec/spec.py:1132-1176`) is the named
   anti-pattern.

### 3.2 Divergences

- **Prevent vs repair:** kernels and neo4j prevent (locks); Oak arbitrates
  and repairs (first-committer-wins + default-on GC); juicefs tolerates and
  loops (ENOTEMPTY churn, retries). The split tracks what each can afford:
  in-process locks are cheap, cross-node locks are not.
- **Writer-vs-writer optimism has no precedent.** The kernel's optimistic
  machinery is reader-only; ladybug admits one writer; Oak arbitrates on a
  shared document. No surveyed system lets two writers race lock-free with
  nothing shared to conflict on — vfs's current posture is past the edge of
  the field, which is why the guard must be airtight rather than
  probabilistic.
- **Token granularity:** one global counter (Linux) → per-connection epoch
  (FUSE) → quantized global revision with a caller dial (SpiceDB) → binary
  cache bypass (openfga). The field tolerates coarse; it punishes tokenless.
- **Isolation strategy:** gel pins its whole cluster SERIALIZABLE and owns the
  40001s; juicefs pins MySQL RR but leaves Postgres at READ COMMITTED; AGE
  runs at default and ships the hole. Nobody solves this class *with*
  isolation while spanning heterogeneous engines — consistent with vfs's
  READ COMMITTED topology pin being load-bearing and untouchable.
- **Plan 9 removes the verb:** 9P's wstat renames only within a parent; no
  message takes two directories, so cross-directory topology races are
  inexpressible (`plan9/sys/man/5/stat:191-193`). The radical option — not
  available to vfs (move is contracted) but a useful outer bound.

---

## 4. Leans

Stated as leans with the strongest counter; what precedent cannot settle is
flagged. vfs-specific constraints the field cannot rule on: the materialized
path cache is ratified, storage owns no background work, 10k batches are
contract, topology is pinned READ COMMITTED.

1. **Guarded bump: land it, engine-uniform in mechanism but engine-aware in
   0-row interpretation.** juicefs is a shipped implementation on vfs's
   engines; the MySQL-RR ambiguity (0 rows → retry, not fail) is a declared
   per-dialect fact. *Counter:* juicefs's guard protects a schema that cannot
   tear; vfs's must carry more load — hence §7.1's stricter shape (path-at-
   snapshot predicate, whole-batch abort) is right and prior art does not
   license softening it.
2. **Reverse ordering: prefer giving the write a conflict surface on the
   parent (generation/stamp) over re-running the descendant SELECT.** Oak's
   commit-root-on-parent closes both orderings symmetrically without
   re-collection; a per-mount counter has Linux-grade precedent for
   coarseness. Re-collect-after-reparent (FreeBSD's shape) is the fallback
   that needs no schema change but closes only the delete side and must
   re-run on every topology verb. *Counter:* every write bumping a parent
   stamp adds a hot-row write to the batch path — the SkipDirMtime story
   shows the pressure this creates; precedent cannot settle vfs's throughput
   tolerance at 10k-batch scale.
3. **Residual purge window: write-side parent revalidation, not purge-side
   anything, not an FK.** Oak and AGE bracket the argument: uncommitted
   rivals are invisible to any purge-side read by definition; the engine
   won't object without an FK; the field's minimum sufficient fix is
   neo4j's — assert the parent live *under your own serialization* at attach
   time, which for vfs is the guarded bump's predicate extended to "live and
   in place" (the S_DEAD check in SQL clothing). Pair with a fenced orphan
   sweep as backstop. *Counter:* the FK is the only zero-code engine-level
   backstop, and no peer runs vfs's exact combination (path cache + bulk
   ingest); but every peer on these engines declined FKs for the same
   bulk-load reasons, and none regretted it — with fsck.
4. **Content-row leak: adopt the ordering rule now (entry rows first, side
   tables from the same id set), and a fenced orphan-content reclaim in
   sweep.** juicefs/seaweedfs ordering discipline plus the age-fence GC
   pattern; the one-time reconciliation for already-leaked rows is juicefs's
   refs<=0 sweep. *Counter:* juicefs's full pattern includes a durable intent
   row, which implies a drainer vfs's no-background-work rule forbids — the
   within-invocation sweep composition is the compliant subset, and precedent
   (SQLite/amcheck/Oak-MBean) says it is the majority pattern anyway.
5. **Copy tear: single joined read.** minio's one-handle pattern is the
   strong precedent and §7.2 already names the mechanism
   (`content_joined()`); the opendal pinned-second-read pattern is the
   fallback if memory budgeting forces two reads at 10k scale, with mismatch
   surfaced as typed conflict. Precedent is unequivocal here; no counter
   worth recording.
6. **Classification: SAVEPOINT-translate or retry-and-reprobe, but decide
   per-verb with the verb as classification input.** opendal's seam + gel's
   40001 translation + pyfilesystem2's operation-shaped tables give the full
   recipe; juicefs's duplicate-key-retryable shows the reprobe alternative
   needs no savepoint machinery. Path attribution must be in the caller's
   namespace (unwrap_errors precedent). Also consider opendal's tri-state
   retryability (persistent-after-retries) over the boolean flag. *Counter:*
   none structural; the only open choice is mechanism, and both are
   precedented.
7. **Detection/repair: ship the fsck verb; it is the missing half of the
   no-FK position.** Two-way path-vs-parent-chain disagreement (Oak's
   Consistency), report-only default with typed findings as Result
   observations (amcheck/SQLite), constructive path-repair behind a flag,
   destructive orphan deletion behind a separate opt-in with
   ambiguity-as-veto (minio/seaweedfs). Run the thorough variant under the
   per-mount topology serialization (amcheck's lock-tier), or age-fence the
   cheap one. The repair deadline (trash retention window, §7.4) argues for
   folding the detector into sweep so it runs as often as retention does.
   *Counter:* none found — this is the strongest consensus in the survey.
8. **The path-keyed vs parent_id-keyed split (§7.3): lean id-closure for
   collection, path as derived cache.** Every survivor of concurrent
   relocation anchors operations to ids and treats paths as derived,
   revalidated-or-locked state (FUSE nodeids, kernel parent chains, edge
   tables); the id-closure purge self-heals legacy torn rows by construction.
   *Counter, worth recording in 086's tradeoff table:* the path cache buys
   real things — one-query lookup, and nearly-free loop detection (juicefs's
   edge design carries an open TODO admitting it doesn't check
   move-into-own-subtree, `juicefs/pkg/meta/sql.go:2358`). Prior art does not
   demand dropping the cache; it demands exactly one authoritative
   representation, with the cache repaired from it.
9. **Regression tests: build bespoke two-instance natural-timing races.**
   pjdfstest — the industry's executable POSIX contract — contains zero
   concurrency tests (grep for concurrent/parallel/race matches nothing
   across `pjdfstest/tests/`). There is no corpus to borrow; §7.5's demand
   stands. Oak even ships a command to *manufacture* orphan states for GC
   testing (`oak-run/.../CreateGarbageCommand.java:64-105`) — precedent for
   making the torn state a first-class, test-generable citizen.

---

## 5. Gaps — what the surveys could not ground

- **MSSQL and Oracle have no prior art in this problem space.** juicefs's SQL
  meta supports only sqlite/mysql/postgres; Oak's RDB backend was not
  examined; SpiceDB is Postgres/CRDB/Mongo. The guard's 0-row semantics and
  retry taxonomy on MSSQL/Oracle must be derived from vfs's own conformance
  runs (and the campaign's MSSQL storm legs never completed — §6 of the
  report).
- **No precedent for two lock-free writers with vfs's dual representation.**
  The nearest cousin — libfuse's high-level API, the one component presenting
  materialized paths over an id store — concluded it needed per-ancestor-chain
  reader-writer locking (`libfuse/lib/fuse.c:995-1075`). The multi-writer
  version of vfs's torn write is unrepresentable there; the guard machinery
  carries load nothing in the field has carried.
- **neo4j's read-side anomaly contract** (traversals at read-committed
  observing concurrent structural change) is grounded only by the absence of
  read-side locks in the paths reviewed, not by in-repo prose.
- **Oak's cross-cluster add-vs-delete acceptance** is inferred from the
  existence of orphan GC modes, not from an explicit in-repo statement; its
  conflict-handling design doc is an empty stub (`documentmk.md:1065`).
- Assorted unexamined corners flagged by the surveys: juicefs sustained-
  session handling, sqlite's `.recover` repair path, opendal's generic
  read-then-write copy fallback, seaweedfs's above-store protection for
  DeleteFolderChildren, ladybug's multi-write conflict detection behind its
  non-default flag, TerminusDB's head-advance CAS primitive.
- **License flag (action item, not a research gap):** the `minio` reference
  clone is AGPL-3.0, which violates the CLAUDE.md keep-only-permissive-clones
  policy. All minio evidence above is describe-and-cite only (no code copied,
  per the universal rule), but the clone should be deleted and the citations
  re-grounded in MinIO's public docs if they need to be re-verified later.
  All other cited repos are permissive (Apache-2.0/MIT/BSD/public domain/
  PostgreSQL license).
