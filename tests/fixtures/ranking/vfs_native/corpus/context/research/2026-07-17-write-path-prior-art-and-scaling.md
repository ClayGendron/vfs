# Write-path prior art: the process of writing a file, and a backend-agnostic scaling plan

- **Status**: research memo (commits us to nothing; feeds a future ADR)
- **Date**: 2026-07-17
- **Owner**: Clay Gendron
- **Question**: What is "the process of writing a file" across mature prior
  art, how does our SQLAlchemy write pipeline map onto it, and what has to
  change for the design to scale to large writes and thousands of
  concurrent users — in particular, can the per-mount revision counter go?

Sources: read-only study of sibling checkouts under `~/Git/Repos/` —
kernels (`linux`, `freebsd-src`, `plan9`), filesystems-on-databases
(`juicefs`, `jackrabbit-oak`, `agentfs`, `libsqlfs`), object stores and
abstraction layers (`minio`, `seaweedfs`, `opendal`, `filesystem_spec`,
`pyfilesystem2`), and database engines (`sqlite`, `postgres`, `turso`,
`sqlalchemy`). Citations are repo-relative to those checkouts. Our own
code cited from `src/vfs/storage/backends/database/`.

---

## 1. The canonical process of writing a file

Every mature system studied — three kernels, four filesystems-on-stores,
four object stores — implements the same skeleton, differing only in the
primitive used at each stage:

1. **Gate** — permission, mode, and bounds checks before touching state
   (Linux `vfs_write`, `fs/read_write.c:668`; FreeBSD `fget_write`,
   `sys/kern/sys_generic.c:527`; Plan 9 `fdtochan`).
2. **Resolve** — path → object, creating through the parent under the
   parent's lock only (Linux `lookup_open` → `vfs_create`,
   `fs/namei.c:4406`; ext4 puts inode-alloc + dirent-add in one
   journal transaction, `fs/ext4/namei.c:2813`).
3. **Arbitrate** — take an exclusive lock scoped to *one file object*:
   Linux per-inode `i_rwsem` (`mm/filemap.c:4465`), FreeBSD per-vnode
   lock, fossil per-`File` QLock, JuiceFS `SELECT ... FOR UPDATE` on one
   inode row (`pkg/meta/sql.go:3359`), MinIO per-object namespace lock
   (`cmd/erasure-object.go:1553`). **Nothing global.** Writers to
   different files never share a lock in any studied system.
4. **Stage data invisibly** — the payload lands somewhere readers cannot
   see: page cache (kernels), object-store blocks uploaded before any
   metadata exists (JuiceFS `pkg/vfs/writer.go`), temp uuid paths
   (MinIO `minioMetaTmpBucket`), uncommitted-revision documents (Oak),
   temp file (fsspec local, `implementations/local.py:401`).
5. **Publish with one small, constant-size, atomic commit** — a rename
   (MinIO `renameData`, `cmd/erasure-object.go:1019`), one row
   insert/upsert whose blob is a chunk manifest (SeaweedFS
   `abstract_sql_store.go:181`), one conditional single-document update
   (Oak's commit-root, `Commit.java:481-516`), a multipart
   complete-with-part-list (S3/OpenDAL). The publish step's cost never
   scales with payload size.
6. **Propagate ancestors and aggregates asynchronously** — the parent /
   root is *not* updated on the write path: Oak accumulates `_lastRev`
   ancestor markers in memory and background-flushes them, touching the
   root **once per ~1s cycle** no matter how many commits landed
   (`UnsavedModifications.java:134-215`); JuiceFS batches directory
   stats the same way (`pkg/meta/quota.go:181-250`). Kernels defer
   timestamps/size persistence to writeback.
7. **Make durable in batches** — group commit everywhere: jbd2 batches
   many files' metadata into one running transaction and adaptively
   waits so concurrent fsyncs share one commit
   (`fs/jbd2/transaction.c:1949-1974`); Postgres piggybacks WAL flushes
   across committers (`xlog.c:2869-2906`); SQLite WAL defers the main-db
   fsync to checkpoints.

Cross-cutting laws worth stating explicitly:

- **Law of local locking.** The only exclusive lock held for the duration
  of a write is per-file. Global structures are either lock-free,
  sharded, attach-in-O(1) (jbd2's running transaction), or batched
  (counters, below).
- **Law of the invisible payload.** Bytes are placed before they are
  named. Failure before publish means orphaned garbage to GC — never a
  torn visible state. Every system pairs this with a reaper (MinIO's
  stale-upload sweeper, `erasure-multipart.go:134-205`; SeaweedFS's
  deletion queue, `filer_deletion.go:584`).
- **Law of the cold counter.** Nobody allocates ordered IDs per write
  from shared transactional state. Oak's revisions are
  `(timestamp, local counter, clusterId)` with **no cross-node
  coordination at all** (`Revision.java:177-195`); JuiceFS batches 1024
  inode / 4096 slice IDs per counter touch with jittered prefetch
  (`pkg/meta/base.go:50-65, 1506-1557`); Postgres sequences are
  deliberately non-transactional and cached precisely so allocation
  never serializes commits (`src/backend/commands/sequence.c:625-679`).
  Where ordering is needed, systems use watermarks/fences or commit
  timestamps (Turso MVCC `begin_ts`/`commit_ts`,
  `core/mvcc/database/mod.rs:839-894`), never dense ordered counters.
- **Law of optimistic retry.** Conflicts surface as retryable outcomes,
  classified per engine, retried with backoff: JuiceFS's 50-try
  quadratic-backoff loop with per-dialect `shouldRetry`
  (`pkg/meta/sql.go:1198-1266`); Oak's rebase-with-backoff that suspends
  until the conflicting revision is visible
  (`DocumentNodeStoreBranch.java:177-222`); Postgres SQLSTATE `40001`
  contract; SQLite `SQLITE_BUSY`.

The cautionary counter-examples are equally instructive: libsqlfs and
agentfs put content read-modify-write inside one big transaction over a
single connection — perfectly correct, and structurally incapable of
concurrent writers (agentfs pins `MAX_CONNECTIONS = 1`,
`connection_pool.rs:14`).

---

## 2. Where our pipeline stands against this map

The current `writes.py` pipeline (see `write-pipeline.md` at repo root
for the method-level diagram) already embodies most of the skeleton:

| Canonical stage | Ours today | Verdict |
| --- | --- | --- |
| Gate | `_Plan` gates: `outside_trash`, `within_budget`, `parent_gate` | ✅ matches; pure staging pass, error-free plans only |
| Resolve | `_fetch_committed` one `path IN` select; `mint_chain` parents-before-children | ✅ matches ext4's create-in-one-txn shape |
| Arbitrate | `UNIQUE(parent_id, name)` upsert / catch-retry per dialect | ✅ matches; per-row, no global lock |
| Stage invisibly | plan-then-execute inside one txn | ✅ for metadata; ❌ content rides the same txn (large writes = giant txns) |
| Small atomic publish | the batch commit | ✅ for small files; ❌ cost scales with content size |
| Async ancestor propagation | ❌ parent bumps are synchronous rows in the write txn | hot-row risk under fan-in |
| Batched durability | one txn per batch; engine group commit does the rest | ✅ |
| Optimistic retry | `with_retry` + `is_retryable` SQLSTATE classification (`dialects.py:124`) | ✅ already the JuiceFS template |

**The one structural violation is revision allocation.**
`allocate_revisions` (`writes.py:105`) claims a range from the per-mount
`revision_counter` row and holds that row's lock to commit, so commit
order equals allocation order. Consequences by engine (from the
`postgres`/`sqlite` study):

- SQLite: harmless — WAL already enforces one writer
  (`src/wal.c:3715-3718`); the counter adds nothing.
- Postgres: a manufactured global mutex. Every writer to a mount queues
  in `XactLockTableWait` behind the counter row's holder
  (`heapam.c:3587-3591`), collapsing MVCC's row-level parallelism to ~1
  writer per mount and bloating the hot row with dead tuples. This is
  precisely the pattern the sequence machinery exists to avoid — and
  sequences can't substitute here because their values are cached,
  gapped, and commit-order-decoupled by design.

So: correct, portable, and the single ceiling on per-mount write
throughput. Everything below is about removing it without losing what it
pays for.

---

## 3. The revision stamp: four jobs, one of which forces ordering

What `revision` is load-bearing for today:

1. **Lost-update guard** — `revision = base` in every material UPDATE's
   WHERE (`writes.py:770`); the only defense at READ COMMITTED
   (2026-07-13 write-pipeline memo, §"Postgres").
2. **Snapshot coordinate** — `Observation.revision`; envelope merge nulls
   it on disagreement (`envelope.py:385`).
3. **Namespace-change signal** — parent bumps for future list caching.
4. **Grep-index watermark** — epoch fingerprint records
   `max revision at build`; dirty overlay is `WHERE revision > watermark`
   (2026-07-13 grep-index memo §3). **Only this job needs mount-wide,
   commit-ordered values** — and only at reindex time.

Jobs 1–3 need *per-entry monotonicity only*: `SET revision = revision + 1`
guarded on the old value gives all three with zero cross-writer
coordination — the standard optimistic-lock design, and the moral
equivalent of Oak allocating revisions without cross-node coordination.

Job 4 does not actually need ordered *revisions* either — it needs a way
to know **which rows the published index does not cover**. Prior art
offers two replacements:

- **Fence at reindex** (what `allocate_revisions`' own docstring
  anticipates, `writes.py:110-114`): allocate from a sequence, and have
  reindex capture its watermark under a brief writer fence / in-flight
  drain. Portable-but-fiddly; Postgres gets the horizon free
  (`pg_snapshot_xmin`), the generic floor does not.
- **Explicit dirty flags** (chosen direction, below): make index
  coverage row state instead of an ordering predicate. No fence, no
  ordering property, fully portable.

**Direction (Clay, this session): per-entry versions, plus index-status
flags on chunks.** The schema is already half there: `entries.chunked` /
`entries.encoded` exist, are indexed, and every write path already
stamps them `False` transactionally (`entry.py:384-404`, `writes.py:760`,
`writes.py:822`). The change is to *use* them as the grep dirty set:

- Overlay predicate becomes `WHERE NOT encoded` (scan side) /
  `WHERE encoded` (index side) — the two territories are mutually
  exclusive by construction, satisfying the double-hit rule from the
  grep-index memo.
- Reindex processes `WHERE NOT encoded` rows and flips flags with a
  **version-guarded** update: `SET encoded = true WHERE id = :id AND
  revision = :seen` — the same optimistic guard as job 1, which closes
  the writer-races-indexer window with no fence.
- Per-chunk flags (on `chunks` rows) extend the same idea so a large
  file re-embeds/re-indexes only the chunks whose content changed,
  rather than all-or-nothing at the entry level.
- The epoch fingerprint keeps its format-version and options-hash parts
  (drop-and-rebuild triggers); the *watermark* part is superseded by the
  flags. Old-epoch posting rows still verify against live entries, so
  stale candidates stay harmless.

What is genuinely lost: a mount-wide total order ("give me everything
that changed since T"). Nothing live depends on it today; if a change
feed is ever needed, `updated_at` plus per-entry versions covers
near-term uses, and a dedicated append-only change table (written in the
same txn) covers exact ones.

**Resolved 2026-07-17 (Clay):** the mount-wide change cursor *is*
`updated_at`. No change-log table, no revived ordered allocation.
Consequence to state honestly in the ADR: `updated_at` is a coarse
cursor — wall-clock, tie-prone within a timestamp's resolution, and
skew-prone if app servers stamp it — so "changed since T" consumers must
query with slack (T minus a safety window) and dedupe by per-entry
version; it is not an exact total order, and nothing may treat it as
one.

---

## 4. The plan: a backend-agnostic write path for large writes and thousands of writers

Proposed end-state, each piece grounded in the prior art above. This is
research-stage; the commitment happens in an ADR.

### 4.1 De-serialize revisions (the unlock)

- Drop `allocate_revisions` and `meta.revision_counter` from the write
  path. Creates start at `revision = 1`; material updates do
  `revision = revision + 1` guarded on the read value; the
  arbitration-clobber arm stays unguarded as today.
- `_finish`/observations report the per-entry value — still "equal to a
  post-commit stat", job 2 intact.
- Removes 2 of the 7 round trips and the per-mount lock queue outright.
  Per-mount throughput ceiling moves from "one writer at a time" to the
  engine's real limit (Postgres: row-parallel; SQLite: unchanged WAL
  single-writer, now without pretending otherwise).
- `traits()` `revision_encoding` changes meaning: `counter64` (mount-
  ordered) → per-entry monotone. Callers of the protocol trait need the
  rename audit.

### 4.2 Index status as flags, not watermark (per §3)

Entry-level `chunked`/`encoded` as the dirty set; per-chunk flags for
partial re-index of large files; version-guarded flag flips in reindex;
epoch fingerprint keeps format+options, loses the watermark.

### 4.3 Ancestor propagation off the write path (the hot-row fix)

Parent bumps are the remaining shared-row write: N writers into one
directory serialize on the parent's row at commit. Both Oak and JuiceFS
solve this identically — accumulate in memory, background-flush batched,
newest-revision-per-path (`UnsavedModifications.java:71-91`,
`quota.go:181-250`). For us:

- Near term (correct, simple): keep the bump but make it the *last*
  statement and fold it into the guarded-update executemany — it already
  is unconditional and last; contention is real only under heavy same-
  directory fan-in.
- At scale: move namespace-change signaling off the parent row entirely.
  Options: (a) an in-process accumulator + background flusher in the
  MCP server (Oak-style; requires a place for the background task and
  crash-recovery semantics), or (b) derive directory change from
  children at read time (`MAX(updated_at)` over the `parent_id` index)
  and drop stored parent bumps.

  **Resolved 2026-07-17 (Clay):** storage owns no background work —
  (a) is off the table, for the parent bump and everywhere else (the
  §4.4 reaper stays inside admin verbs, never a daemon). The at-scale
  path is (b): directory change state derives from children at read
  time via the `parent_id` index, and stored parent bumps leave the
  write path. Until (b) lands, the near-term synchronous bump is
  acceptable contention.

### 4.4 Large writes: stage content invisibly, publish small (the JuiceFS/SeaweedFS shape)

Today content rides the batch transaction, so a 100 MB write is a 100 MB
transaction — the libsqlfs failure mode. Target shape:

- **Stage**: content chunks written in independent, small, bounded
  transactions *before* the publishing txn, keyed by an opaque staging
  identity (ULID) invisible to every read (`chunks`/`content` rows with
  no live entry pointing at them — the DB-native analog of MinIO's temp
  uuid / JuiceFS's pre-uploaded blocks). Bounded parallelism per write,
  fsspec-style buffering at the ingestion edge.
- **Publish**: the existing batch transaction writes/updates only the
  narrow entry row (plus small-content inline, SeaweedFS's
  `SaveToFilerLimit` pattern — small bodies skip staging entirely) and
  flips ownership of the staged chunk set. Constant-size regardless of
  payload.
- **Reap**: staged chunks whose publish never arrived are orphans; a
  reaper deletes staging rows older than a horizon (MinIO's stale-upload
  sweeper; SeaweedFS's `DeleteUncommittedChunks`). Runs inside the
  existing reindex/admin verb family, no daemon required.
- `content_hash` is already computed (`entry.py:175`); content-addressed
  staging gives idempotent retries (re-staging the same bytes is a
  no-op) and cross-version dedup as a free option later.

### 4.5 Concurrency mechanics (mostly already right)

- Retry discipline: `with_retry` + SQLSTATE classification is already
  the JuiceFS template; keep. Add jittered backoff if not present.
- Isolation: keep Postgres op-txns at REPEATABLE READ (rivals surface
  as 40001 → retry); the read-back in `_update_materials` stays — it is
  the portable floor's lost-update detector, per its docstring.
- Batching: bulk inserts already ride `insertmanyvalues`
  (`engine/default.py:248-444`); dialect budget already read off the
  live dialect. UPDATE/DELETE get no executemany-RETURNING portably —
  the verification read-back pattern is the right portable choice.
- Pool sizing is the real admission valve: default QueuePool is
  5+10 overflow (`pool/impl.py:75-76`). "Thousands of users" means
  thousands of MCP sessions multiplexed onto tens of DB connections —
  document pool sizing as deployment guidance, don't chase per-user
  connections.

### 4.6 Round-trip budget after the plan

Single-file create: fetch(1) + insert(1) + content(1, inline) + bump(1)
= **4** (from 7). Overwrite: fetch(1) + guarded update(1) + read-back(1)
+ content(1) = **4**. Large write: publish txn stays ~4 regardless of
size; staging txns proportional to payload but individually small,
parallel, and outside any lock. `_replace_content`'s delete+insert can
become a dialect-profiled upsert (−1 more) when worth it.

### What we deliberately keep giving up vs POSIX

Same trades as JuiceFS/Oak, stated honestly: no cross-batch atomicity;
close-to-open rather than per-write durability for staged large writes
(a crash between stage and publish = the write never happened, plus
reapable garbage); eventual ancestor signals if 4.3(a) is chosen.

---

## 5. Verdict

The current pipeline is structurally sound — plan-then-execute, per-row
arbitration, dialect-classified retry all match prior art. It violates
exactly two of the four laws: the **cold-counter law** (the per-mount
revision counter is a global mutex Postgres cannot forgive) and the
**invisible-payload law** (content size dictates transaction size). The
fix for the first is per-entry versions + flag-based index dirty sets
(§3, §4.1–4.2), which the schema already anticipates; the fix for the
second is stage-then-publish content (§4.4), which the content/chunks
table split already anticipates. The parent-bump hot row (§4.3) is the
one place needing a genuine decision about background work.

Next step: an ADR covering §4.1–4.2 (the revision split), with §4.3–4.4
either bundled or staged behind it.
