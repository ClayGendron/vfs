# 072 research — write pipeline: transactions, revision, versions, delete, from source

- **Date:** 2026-07-13
- **Status:** verified — 2026-07-13; Phase 3 refutation pass applied
  (18 claims: 17 confirmed, 1 miscited-fixed, 0 extrapolation-flagged,
  0 refuted-cut)
- **Method:** the `research.md` / `research-grep-index.md` protocol —
  nine parallel researchers (linux-vfs, linux-journal, plan9,
  unix-history, sqlite, postgres, git, prior-roster re-reads,
  literature) over local checkouts and canonical papers, each grading
  every question **supports / contradicts / nuanced / no-precedent**
  with file:line (or paper §) evidence, adversarially instructed,
  extrapolations flagged. Companion: `research-read-pipeline.md`
  (R1–R8). Read-side findings are cited here only where questions
  overlap (W6↔R8 error order, W7↔R4 consistency).
- **Questions under evaluation** (`research-pipelines-brief.md`):
  - **W1** — transaction shape and ordering (spec §3, §10)
  - **W2** — revision encoding and semantics (spec §5); grades the
    research.md "no filesystem precedent" claim
  - **W3** — version chain design; is snapshot-every-10 defensible (§9)
  - **W4** — content layout: inline blob vs chunk rows vs out-of-line
    (§3, §9)
  - **W5** — batch write discipline; the constant-statement criterion
  - **W6** — rename/move/delete atomicity and the delete model —
    **resolves the §9 soft-delete marker** (§9, §10)
  - **W7** — concurrent writers and arbitration (§10)
  - **W8** — durability and crash consistency; enumerate the windows
    (§10)

## Bottom line

The spec's write spine — one session per op, one commit per batch,
unique-index arbitration, no correctness-bearing in-process state —
survives review with kernel-grade precedent behind it. Three questions
resolve outright. **W2:** research.md's "no filesystem precedent for
revision" is overturned three independent ways (Linux `i_version`, 9P
`qid.vers`, the NFSv4 mandatory change attribute); encoding resolves
to a backend-owned 64-bit integer counter stamped inside the write
transaction, covering metadata-only mutations, with namespace changes
bumping the *parent's* revision too. **W6:** the §9 soft-delete marker
resolves to **trash-reparent** (the JuiceFS model) with an explicit
reclamation sweep verb — the hand-threaded `deleted_at` predicate has
no precedent in any reviewed system — and cross-directory move gains a
duty the spec missed: cycle refusal must run under a serialization
point that freezes tree topology (the 4.4BSD rename bug), which
SQLite's single writer gives free but Postgres does not. **W8** is the
sharpest contradiction of the spec as written: "committed" is
undefined against power loss at SQLite's common WAL pairing
(`synchronous=NORMAL` never fsyncs on commit), so the backend pins
`synchronous=FULL` at first touch or declares the durability window as
a trait. Snapshot-every-10 (W3) **survives** — git ships depth-50
chains, so a ≤9-diff bound is comfortable; only the Python
diff-apply throughput number goes to the spike. (Post-spike, the
owner inverted the write side — store-full at write, pack in batch;
interval 10 parameterizes the packed form. See the W3 banner.) Content (W4) moves to
its own node_id-keyed table (the SQLite overflow-chain rewrite hazard
plus TOAST's pointer-reuse precedent). The constant-statement-count
acceptance criterion (W5) is over-strong as written and is restated
per parameter-budget chunk.

## Verdict matrix

S = supports · C = contradicts · N = nuanced · — = no precedent / not
assessed. (Most N/C grades here contradict *research.md's framing or a
spec silence*, not the design direction — the per-question sections
say which.)

| Question | linux-vfs | linux-journal | plan9 | unix-history | sqlite | postgres | git | prior | literature |
|---|---|---|---|---|---|---|---|---|---|
| W1 transaction shape | — | N | — | S | — | S | — | S | S |
| W2 revision encoding | N | — | S | — | N | S | — | N | **C** |
| W3 version chain | — | N | N | — | — | — | N | — | N |
| W4 content layout | — | — | — | — | N | N | — | N | — |
| W5 batch discipline | — | — | — | — | — | — | — | N | — |
| W6 move/delete model | N | N | — | N | — | — | N | N | — |
| W7 concurrent writers | — | — | S | S | S | N | — | S | — |
| W8 durability windows | — | N | N | N | N | S | N | S | S |

(The literature's W2 "C" contradicts *research.md's no-precedent
claim*, i.e. it argues **for** the spec's revision stamp with stronger
evidence than the spec itself cites. The prior-roster W3 cell is a
checked no-precedent: no repo in the nine-repo roster implements
version chains at all.)

## W1 — Transaction shape and ordering: settled

**Resolution: settled.** One-transaction-per-protocol-method stands,
and the review sharpens *why* it is strictly stronger than every
filesystem precedent — plus two sentences §3 must add.

- The entire ordering apparatus of the journaling/soft-updates lineage
  exists to approximate what one SQL transaction grants by atomicity.
  Soft updates enforces exactly three invariants — never point at an
  uninitialized structure, never expose a name before its inode's
  link count is durable, never reuse a resource before nullifying old
  pointers — each documented at its dependency-setup site
  (freebsd-src/sys/ufs/ffs/ffs_softdep.c:5462-5477, 8677-8692,
  7060-7074, 9150-9158), and it needed undo/redo rollback machinery
  because dependent structures share disk buffers
  (ffs_softdep.c:8683-8685, 9199-9208). The literature states the
  same three rules canonically (Ganger & Patt, OSDI '94, §1) and
  credits WAFL's stability to *eliminating* ordering via atomic
  consistency points rather than tracking it (Hitz et al., USENIX
  Winter '94, §5). Inside one commit, all three are satisfied
  trivially (flagged extrapolation in both findings, but the shape is
  arithmetic: atomic commit admits no observable interleaving).
- jbd2 has **no per-operation rollback at all** — its only abort is
  whole-journal shutdown to read-only
  (linux/fs/jbd2/journal.c:2526-2556), and its atomicity unit is a
  timer-batched compound transaction, not an op
  (linux/include/linux/jbd2.h:539-548). Spec §3's
  rollback-on-any-DB-error is an upgrade on the journaling lineage,
  not a port of it. Likewise ext4's `data=ordered` machinery
  (data blocks flushed before the commit record,
  linux/fs/jbd2/commit.c:571-577, 767-773) is absorbed entirely by a
  single-store transaction — **and silently reacquired if content ever
  moves out of the transactional store** (flagged extrapolation;
  linux-journal). That coupling sentence belongs in §3.
- What is *not* free (postgres, nuancing): constraint arbitration
  fires per statement under SnapshotDirty, not at commit
  (postgres/src/backend/access/nbtree/nbtinsert.c:563-601), so
  statement order inside the transaction is load-bearing for
  *conflict timing* even though it carries no crash-consistency
  weight. Pin a canonical order (parents before children, entries
  before versions/edges) so arbitration behaves identically across
  dialects.
- Prior finding reaffirmed: internal helpers MUST NOT open/commit
  transactions (libsqlfs's transaction-per-helper scar, research.md
  §"§3") — the sentence is still missing from spec §3.

## W2 — Revision encoding and semantics: settled; the no-precedent claim is overturned

**Resolution: settled.** The encoding fork in spec §5 ("integer
counter per path vs `updated_at || content_hash`") closes: **64-bit
integer counter, backend-owned, stamped inside the same write
transaction, incremented unconditionally per material write.** And the
research.md §"§5 revision" sentence "No filesystem precedent exists"
is **contradicted at the protocol layer by three independent
sources** — the grade this question was chartered to deliver:

1. **Linux `i_version`** — a kernel-managed, NFSv4-mandated per-inode
   change attribute: "must appear larger to observers if there was an
   explicit change to the inode's data or metadata since it was last
   queried" (linux/include/linux/iversion.h:7-37). Its lazy-increment
   optimization weakens the contract to queried-change detection —
   N writes between two reads may yield one visible increment
   (linux/fs/libfs.c:1984-2032) — but that machinery exists solely to
   avoid extra journal transactions ("if this function returns
   false... we can avoid logging the metadata",
   linux/fs/libfs.c:1998-1999); vfs's revision commits in the same
   row-update transaction, so vfs promises the *stronger* per-write
   increment Linux only approximates (flagged extrapolation,
   linux-vfs). The founding motivation is the counter-over-timestamp
   argument itself: "i_version must appear to change even if the
   ctime does not, since the whole point is to avoid missing updates
   due to timestamp granularity"
   (linux/include/linux/iversion.h:14-20, 255-266).
2. **9P `qid.vers`** — a protocol-level per-file version number
   (plan9/sys/man/5/0intro:429-437), bumped generically by lib9p on
   every successful Twrite (plan9/sys/src/lib9p/srv.c:536-542),
   persisted durably by fossil as `mcount`
   (plan9/sys/src/cmd/fossil/9p.c:646,756,876), consumed by a whole
   ecosystem (mv/cp identity checks, stat-poll change detection,
   kernel mount cache). Every Plan 9 server chose a counter; none
   chose a timestamp or hash.
3. **NFSv4 change attribute** — "both the NFSv4 [RFC7530] and NFSv4.1
   [RFC5661] protocols define the change attribute as being mandatory
   to implement" (RFC 7862 §10), and RFC 7862 §12.2.3's
   `change_attr_type` is a shipped taxonomy of exactly this fork,
   with VERSION_COUNTER at the top of the value hierarchy (it alone
   supports client-side prediction and conflict attribution) and
   time-based encoding permitted "only if the file system object
   cannot be updated more frequently than the resolution of
   time_metadata" (RFC 5661 §5.8.1.4) — a precondition agent-speed
   read→edit→write loops fail, which is the AgentFS mtime scar
   restated as protocol law.

The negative precedent completes the picture (sqlite): **SQLite offers
no free watermark.** `PRAGMA data_version` is a per-connection,
in-memory, lazily-updated invalidation signal that deliberately
excludes the connection's own commits
(sqlite/src/pager.c:669, 6702-6709; sqlite/src/btree.c:4423-4428),
and WAL commits never tick the durable header change counter
(sqlite/src/pager.c:6493-6517). Postgres corroborates the counter
family: every ordering/visibility decision uses xid/cid/LSN counters,
never wall clocks (postgres/src/backend/access/transam/xact.c:
1497-1512). The revision is an application column, full stop.

**Semantics to pin in §5** (the amendments):

- **64-bit.** fossil's 32-bit `mcount` is documented "can wrap!"
  (plan9/sys/src/cmd/fossil/vac.h:61) — the scar to avoid.
- **"Material write" includes metadata-only mutations.** RFC 7862
  §10's mandated constraint covers "the file data or metadata";
  fossil's narrower scoping (metadata-only wstat does not bump the
  target, plan9/sys/src/cmd/fossil/file.c:1719-1723) is the weaker
  precedent — follow the RFC, since `if_revision` guards must catch
  metadata races too.
- **Namespace mutations bump the PARENT directory's revision.** The
  iversion contract makes the filesystem "ALWAYS responsible for
  i_version on directory namespace changes", and ext4 bumps the
  parent on entry add/delete/rename
  (linux/include/linux/iversion.h:39-48; linux/fs/ext4/namei.c:2150,
  2697, 3654); fossil does the same (create/remove/wstat bump the
  parent's mcount, file.c:505,1149). Spec §5 currently omits this —
  without it, future list caching and the §6 watermark cannot see
  membership changes that touch no child row.
- **Backend-owned, never caller-writable** — fossil refuses wstat on
  qid.vers with an error (plan9/sys/src/cmd/fossil/9p.c:148-174).
- **The ordering half of the contract, stated:** a revision value is
  never observable before the state it stamps
  (linux/include/linux/iversion.h:50-54) — free in vfs because both
  commit together, but it is the load-bearing half of the NFSv4
  contract and fossil is the cautionary tale (stamps before the data
  write, never rolls back on failure, file.c:676-711,1704-1717).
- **Declare the encoding as a capability trait** — `change_attr_type`
  is a shipped protocol field whose whole job is declaring revision
  semantics per filesystem so consumers can branch (RFC 7862
  §12.2.3), matching research.md §3's semantic-traits refinement.

## W3 — Version chain design: settled-with-amendments; snapshot-every-10 survives

> **Inverted 2026-07-13 (owner decision, post-spike):** the
> recommendation below — diff-on-write with the git shape as fallback —
> is superseded; spec.md §9 promotes the fallback to primary. Versions
> store **full at write** (no diff, no prior-content read in the write
> transaction) and a batch **pack verb** rewrites cold ranges into the
> snapshot-every-10 + forward-diff form, mirroring §6's batch-only
> indexing doctrine. The evidence below stands unchanged: the spike's
> write-side finding (diff costs 2× the worst read replay at 256 KB) is
> what motivated the inversion, interval 10 becomes the *packed* form's
> parameter, and the read-cost numbers price the packed tier.

**Resolution: settled-with-amendments.** Forward diffs +
snapshot-every-10 stays the v1 design. The chain *shape* is defensible
against every counterpoint reviewed; only one number goes to the
spike: **Python unified-diff apply throughput, measured as
reconstruction latency vs chain length × snapshot interval** (the
already-planned spike, now narrowed).

The honest evidentiary picture is that **no reviewed never-overwrite
system reconstructs by replaying diffs** — the design is
precedent-free on the read-cost side and must carry its own numbers:

- WAFL shares blocks (a snapshot "consumes no disk space except for
  the Snapshot inode itself", Hitz et al. §3.4); LFS keeps versions
  addressable in the log; venti/fossil store content-addressed full
  block trees where "reconstruction cost of any version is
  independent of version count"
  (plan9/sys/src/cmd/fossil/fs.c:501-560; flagged extrapolation from
  the walk structure); btrfs snapshots copy exactly one root block
  (linux/fs/btrfs/transaction.c:1820-1837). The prior nine-repo
  roster has *nothing*: AgentFS lists versioning as an unimplemented
  extension point (agentfs/SPEC.md:480), JuiceFS keeps whole files in
  trash, libsqlfs overwrites in place.
- But the alternatives are priced, not free. btrfs's COW paid "a
  4x-6x higher write load than ext3" and retreated to a bolt-on
  write-ahead tree log for fsync latency
  (linux/fs/btrfs/tree-log.c:238-249), and its version GC is a
  resumable multi-transaction background walk with persisted progress
  (linux/fs/btrfs/extent-tree.c:6234-6247,6305-6320). venti's GC
  answer is "never delete" (the protocol has no delete message,
  plan9port/include/venti.h:256-274) — an exit only content-address
  dedup affords. Forward diffs keep GC trivial (delete rows for a
  path) at the cost of bounded chain replay.
- **The bound is comfortable.** git — the one system that does ship
  delta chains — hard-caps depth at 50 by default with the documented
  rationale being unpack cost, and papers over chain cost with a
  96 MiB decompressed-base LRU cache rather than shortening chains
  (git/builtin/pack-objects.c:227-229;
  Documentation/config/core.adoc:447-456 — `core.deltaBaseCacheLimit`,
  "Default is 96 MiB on all platforms"). vfs's worst case is 9
  applications — 5× tighter than git's default tolerance (flagged
  extrapolation, git researcher). The interval *pattern* is
  independently precedented as checkpoint-plus-bounded-replay
  (Rosenblum & Ousterhout, TOCS 1992, §4.1), with the caveat that the
  constant is a measured quantity, not a designed one — Sprite's own
  30s guess was self-described as "probably much too short".

Amendments to §9:

1. **Verify the content hash on write as well as read** — libventi
   double-checks both directions by default
   (plan9port/src/libventi/client.c:89-96,127-135); the write-side
   check catches corruption before it is durable.
2. **Hash mismatch on reconstruction classifies as a dedicated
   corruption kind** — distinct from not_found and generic internal —
   naming the version and chain position that failed. git's
   bad-object bookkeeping is the precedent that corrupt ≠ missing
   (git/packfile.c:983, 1637-1663; git/odb.c:607-614). No prior-roster
   repo ever classified this because none reads history back.
3. **Record the firewall property:** a corrupt diff row poisons
   reconstructions only until the next snapshot, so the interval also
   caps corruption blast radius to ≤9 versions — a second,
   independent justification for periodic snapshots (flagged
   extrapolation, git researcher).
4. **Record the write-path cost the choice buys:** creating a version
   row requires reading the previous version's content inside the
   write transaction (vfs/src/vfs/models/versioning.py:148-171) — a
   read amplification git's snapshot-on-write deliberately avoids
   (git/object-file.c:750-808). If the spike measures write latency
   badly, the precedented fallback is store-full-on-write +
   batch-time delta compression (git's shape, mirroring §6's
   batch-only doctrine) or content-addressed whole versions
   (venti's), **not** deeper snapshot intervals.
5. **`content_hash` doubles as the dedup/idempotence hook** — git's
   hash-then-skip write path (git/odb/source-loose.c:615-620) is the
   precedent that identical-content writes can be detected cheaply.
6. Version deletion should be O(pointer), not O(chain-rewrite) —
   WAFL deletes a snapshot by zeroing one inode (Hitz et al. §4.2).
   A diff chain inverts this for intermediate versions; the GC story
   (W6) must state how intermediate version rows die.

## W4 — Content layout: settled-with-amendments; content gets its own table

**Resolution: settled-with-amendments.** The open "single inline blob
column" lean becomes a directed choice: **content lives in its own
table, keyed by node_id, one blob per row, blob column physically
last** — not inline in the entries row. The size-threshold and
page-size numbers stay with the spike.

- The disqualifying hazard is SQLite's overwrite rule: an UPDATE
  whose record changes byte size at all frees and rewrites the entire
  cell *including every overflow page*; only byte-identical-size
  updates take the in-place path
  (sqlite/src/btree.c:9500-9509, 9267-9331). Integers are stored as
  variable-length serial types, so §5's per-write revision counter
  crossing a varint boundary — or any metadata column changing
  length — forces a full overflow-chain rewrite of an unchanged
  multi-MB blob on a metadata-only update (flagged extrapolation,
  sqlite researcher). A wide entries row with inline content is
  structurally hostile to the revision stamp.
- The projection win is physical, not just wire-level: record
  decoding is front-to-back, so a projected-out *trailing* blob's
  overflow chain is never fetched (sqlite/src/btree.c:5102-5130) —
  hence blob-last column order.
- TOAST is the shipped shape of the decision (postgres): a ~2 KB
  threshold hybrid — compress first, then chunk rows keyed by an
  immutable valueid at ~1996 B/chunk
  (postgres/src/include/access/heaptoast.h:28-61;
  toast_internals.c:283-349) — whose unchanged-value pointer reuse on
  UPDATE rewrites zero content bytes on metadata-only writes
  (postgres/src/backend/access/table/toast_helper.c:59-97). That is
  the direct precedent for the acceptance criterion "rename rewrites
  zero content rows".
- The libsqlfs scar is re-scoped by two researchers independently:
  the defect was **path-keyed** blocks, not chunking — TOAST's
  (valueid, chunk_seq) and AgentFS's fs_data(ino, chunk_index) are
  shipped id-keyed chunk designs
  (agentfs/sdk/rust/src/filesystem/agentfs.rs:542-548). Both peers
  chunk because they serve FUSE offset I/O; vfs's whole-document MCP
  verbs remove that reason, so one-blob-per-row stands, with id-keyed
  chunk rows as the legitimate fallback if the spike finds a cliff.
- **Do not build on `sqlite3_blob_*` for v1**: handles cannot resize
  values, die on any row write (SQLITE_ABORT via
  invalidateIncrblobCursors), and hold a transaction open across
  calls (sqlite/src/vdbeblob.c:24-34, 396-406;
  sqlite/src/btree.c:9479-9483) — all three collide with
  one-session-per-op. Record it only as the escape hatch for a future
  streaming/ranged-read verb.
- If content columns are ever compressed, random-access reads degrade
  to prefix decompression (TOAST slices only uncompressed values,
  postgres/src/backend/access/common/detoast.c:200-277) — decide
  compression per column with incremental-read needs in mind.

## W5 — Batch write discipline: settled-with-amendments

**Resolution: settled-with-amendments.** The acceptance criterion "a
1,000-entry batch write executes in a constant number of SQL
statements" is **over-strong as written** and gets restated.

- JuiceFS — the strongest production SQL-FS — never promises constant
  statement count: every bulk write is chunked by a per-dialect
  bind-parameter budget, `getTxnBatchNum()` = 999/19 ≈ 52 rows on
  sqlite3, 65535/19 ≈ 3449 on mysql, 1000 on postgres
  (juicefs/pkg/meta/sql.go:5173-5184), with a generic 200-bean
  slice in `mustInsert` (sql.go:1021-1034). Modern SQLite's default
  SQLITE_MAX_VARIABLE_NUMBER (32766 since 3.32) makes 1,000 narrow
  rows fit one statement, but MSSQL (2100 params) and
  legacy-configured SQLite fail the criterion structurally (flagged
  extrapolation, prior-roster).
- **Restated criterion:** an N-entry batch executes in O(tables
  touched) statements *per parameter-budget chunk*, with the budget a
  declared per-dialect datum on the base class (matching research.md
  §1's "per-dialect deltas as data" refinement).
- Two anti-patterns not to inherit from the same source: JuiceFS's
  `doBatchUnlink` runs **one transaction per chunk** — a mid-batch
  failure leaves earlier chunks committed — and silently `continue`s
  past vanished entries (juicefs/pkg/meta/sql.go:2803-2810,
  2865-2872). Spec §3 must pin the opposite: a vfs batch is ONE
  transaction even when statements chunk, and every entry gets a
  classified per-entry outcome, never a silent skip.
- Correction to the prior doc: research.md's `DirBatchNum = 4096`
  citation is the directory-*listing* fetch batch, not a write budget
  (juicefs/pkg/meta/base.go:58-63; sql.go:6065-6075) — right ceiling,
  wrong pipeline. The heterogeneous-delta idiom worth stealing is the
  single CASE-WHEN update per chunk (sql.go:1036-1076).

## W6 — Move/delete atomicity and the delete model: settled — trash-reparent

### 6a. The delete model — resolves the §9 open marker

**Resolution: settled. Adopt trash-reparent; retire the `deleted_at`
chokepoint.** Three delete models were on the table; the evidence
sorts them cleanly:

- **The `deleted_at` chokepoint has no precedent anywhere in the
  review.** Git has no soft-delete marker (deletion is a new tree
  state; reclamation is reachability GC, git/builtin/prune.c:84-110);
  the FFS lineage's shipped shape is "namespace removal synchronous,
  storage reclamation asynchronous and owned"
  (freebsd-src/sys/ufs/ffs/ffs_softdep.c:9150-9158, 2645-2655); the
  unix-history researcher's direct verdict: "a hand-threaded
  deleted_at predicate has no precedent here." The one prior-roster
  system with reversible deletes (JuiceFS) encodes liveness in the
  namespace, not in a predicate.
- **Hard-delete-in-one-txn is crash-safe with zero extra machinery** —
  the ext4 orphan list exists only because a filesystem's logical
  delete spans transactions (linux/fs/ext4/orphan.c:89-100); a single
  SQL transaction closes that window outright (flagged extrapolation,
  linux-journal). Hard delete is therefore the *simplest sound*
  model, and git is its shipped precedent (hard-delete of the name +
  version history + retention-gated GC).
- **Trash-reparent wins on fit.** It is fully implementation-mapped
  in JuiceFS: delete = remove the original edge, insert a trash edge,
  set Parent = trash **in one transaction**
  (juicefs/pkg/meta/sql.go:2045-2061, 2024-2031); rename-with-replace
  routes the replaced target through the same path (sql.go:2528-2537);
  restore is rename-out with EEXIST classifying as conflict
  (juicefs/cmd/restore.go:65-151); expiry is a decoupled sweep with a
  grace window (juicefs/pkg/meta/base.go:3062-3128). It structurally
  presupposes stable IDs — option (c) synergy — and it satisfies the
  pjdfstest visibility contract by construction (the name vanishes
  from every lookup in the delete transaction). Honest nuance kept
  from the finding: the exclusion predicate does not vanish — it
  becomes a namespace-prefix filter (exclude the trash subtree),
  which merges into the meta-namespace exclusion every read path
  already needs (flagged extrapolation, prior-roster) — still one
  chokepoint, but a path-prefix one instead of `IS NULL` on every
  table.

Why trash-reparent over hard-delete + versions: vfs's callers are
agents; restore-by-move and list-the-trash are verbs the namespace
gives free, the version chain (W3) covers content history either way,
and the delete stays one transaction in both models. The deciding
asymmetry is that trash-reparent keeps the *entry* (id, metadata,
subtree structure) recoverable, not just content bytes.

**The concrete §9 shape:**

- Delete = same-transaction reparent into a time-bucketed trash node
  under the vfs meta namespace (hourly-or-coarser UTC buckets, lazily
  created — JuiceFS's shape, base.go:3019-3050).
- Restore metadata (original parent_id, original name, deleted_at)
  stored as **row columns, never encoded into the entry name** —
  JuiceFS truncates its `{parent}-{inode}-{name}` encoding at MaxName
  with only a logged warning (juicefs/pkg/meta/base.go:3053-3060);
  ULID-named trash entries remove the collision/truncation hazard.
- Restore = move-with-no-replace; target-exists classifies
  `conflict`.
- **Reclamation** (research.md gap #4, in scope here): an explicit,
  idempotent sweep verb with a retention parameter and grace window,
  deleting expired bucket subtrees *plus* their version/chunk/gram
  rows; scheduling is the caller's problem (mirrors the §6
  reindex-verb doctrine). The duty inherited from the orphan-list
  precedent: the trash rows themselves are the durable work queue,
  and the sweep must be safe to re-run after a crash at any point
  (linux/fs/ext4/orphan.c:89-100). Frame it as standing maintenance
  with an owner, not a one-off (FFS runs a permanent flush thread,
  ffs_softdep.c:2645-2655). One transactional advantage to claim:
  the sweep's liveness check and delete run in one transaction,
  closing the concurrency race git documents as unsolved ("users who
  run commands concurrently have to live with some risk of
  corruption", git/Documentation/git-gc.adoc:153-169).
- **Harness probes** (§12): a trashed path classifies `not_found`
  through every read verb (pjdfstest contract); operation under a
  deleted ancestor classifies `not_found`
  (freebsd-src/sys/ufs/ufs/ufs_lookup.c:219-221); after a
  crash-simulated (rolled-back) delete, no row family references the
  others' absence.

### 6b. Move atomicity, cycles, and the concurrency hole

**Resolution: settled-with-amendments — one real spec gap found.**

- **Claim the rename contract; POSIX is not the ceiling.** V7 had no
  rename syscall at all — mv(1) was userspace unlink/link/unlink with
  a window where the target name does not exist
  (unix-history-repo/usr/sys/sys/sysent.c:76-77;
  usr/src/cmd/mv.c:92-118) — and modern FFS still disclaims on-disk
  atomicity ("Best we can do is always guarantee the target exists",
  freebsd-src/sys/ufs/ufs/ufs_vnops.c:1225-1247). One SQL transaction
  delivers what the lineage never had; spec §10 should state it: at
  no point does any reader observe the destination absent during
  replace, both names live, or a partially-moved subtree.
- **The gap: cycle refusal needs a topology-freezing serialization
  point.** Linux serializes every cross-directory rename on a
  per-filesystem mutex precisely because "two innocent renames can
  create a loop together. That's where 4.4BSD screws up. Current
  fix: serialization on sb->s_vfs_rename_mutex"
  (linux/fs/namei.c:5895-5914); the ancestry check is sound only
  because topology is frozen under that mutex (namei.c:3866-3923).
  FreeBSD ships the same shape (per-mount mnt_renamelock,
  freebsd-src/sys/kern/vfs_syscalls.c:3866). Spec §10's
  unique-index-arbitration model covers create/name races but **not
  move-cycle composition on multi-writer engines**: on Postgres under
  READ COMMITTED/REPEATABLE READ, two concurrent moves can each pass
  an in-snapshot recursive-CTE ancestry check and commit a cycle
  (observed 2026-07-13: `spike-results-pipelines.md` §4 composes the
  cycle at READ COMMITTED **and** REPEATABLE READ; SERIALIZABLE aborts
  one; advisory-lock + re-check refuses cleanly — formerly a flagged
  extrapolation). Per engine: SQLite's single-writer
  transaction is a de facto rename mutex — sound as-is; Postgres
  needs a declared choice (per-mount advisory lock on move,
  SERIALIZABLE for the move verb, or commit-time re-verification).
  A pre-check outside that scope is the documented 4.4BSD bug, not a
  design option.
- Cycle refusal is an **ancestry walk to the root** (ufs_checkpath
  climbs '..' chains, EINVAL on source-as-ancestor, EEXIST on
  target == source,
  freebsd-src/sys/ufs/ufs/ufs_lookup.c:1402-1447), never a
  fixed-depth check; the harness tests it at ≥2 depths *plus* the
  two-instances-one-database concurrent case (A→B/x racing B→A/y
  must leave the tree acyclic).
- **Refusal-order rows for the §12 matrix** (feeding the read-doc's
  R8 ladder): for move — source-missing (not_found) before
  target-exists before cycle refusal, and cycle refusal before
  permission checks (linux/fs/namei.c:3866-3923, 1813-1820); Linux
  distinguishes the two cycle directions (source-is-ancestor →
  EINVAL, target-is-ancestor → ENOTEMPTY, namei.c:3896-3909) —
  vfs should either adopt two classified kinds or explicitly collapse
  them, pinned either way.
- No in-process rename serialization is needed on top: FreeBSD's
  mnt_renamelock exists because vnodes aren't transactional; the DB
  transaction (plus the per-engine choice above) is vfs's arbiter —
  confirming the §10 no-in-process-locks default with a named
  precedent.

## W7 — Concurrent writers and arbitration: settled-with-amendments

**Resolution: settled-with-amendments.** The spec's model
(unique-index arbitration, pre-checks as optimizations, no FOR UPDATE
in v1, no in-process correctness locks) is confirmed at source level
on both engines, and the review supplies the mechanism-level sentences
§10 currently lacks:

- **SQLite: BEGIN IMMEDIATE is load-bearing, not stylistic.** The
  busy handler is consulted only when the connection has *no open
  transaction* (`(rc&0xFF)==SQLITE_BUSY && pBt->inTransaction==
  TRANS_NONE`, sqlite/src/btree.c:3746-3747) — deliberate deadlock
  avoidance (btree.c:3590-3603) — so a DEFERRED read→write upgrade
  fails instantly, possibly with SQLITE_BUSY_SNAPSHOT, which no
  in-place retry can fix (the snapshot has forked,
  sqlite/src/wal.c:3685-3739). Opened IMMEDIATE, BUSY_SNAPSHOT is
  downgraded to plain BUSY and busy_timeout absorbs all write-lock
  contention (btree.c:3726-3747). And WAL-mode COMMIT can never
  return SQLITE_BUSY (wal.c:3869-3908) — contention is confined
  entirely to write-transaction start. Classification split: BUSY at
  op start = retryable-in-place (normally invisible under
  busy_timeout); BUSY_SNAPSHOT = discipline violation under
  BEGIN IMMEDIATE — classify loudly, never silently retry.
- **Postgres: the revision guard is the only lost-update defense at
  default isolation.** A row-level write-write conflict never errors
  at READ COMMITTED — the second writer blocks, then EvalPlanQual
  re-evaluates against the newest committed version and proceeds
  (silent last-writer-wins,
  postgres/src/backend/executor/nodeModifyTable.c:1983-2075). So the
  revision guard must appear in the WHERE clause of **every material
  write** (rowcount 0 → conflict), not only caller-requested guarded
  writes — and EPQ's re-check against the latest version is exactly
  what makes that guard sound without SELECT FOR UPDATE, supporting
  the no-FOR-UPDATE default (flagged extrapolation, postgres).
- **Two conflict shapes, two behaviors:** 40001 serialization failure
  (only exists at REPEATABLE READ+) classifies
  retry-whole-transaction; 23505 unique violation is a *definite*
  exists-outcome after wait-then-resolve arbitration
  (postgres/src/backend/access/nbtree/nbtinsert.c:208-241, 563-601,
  669-676) and must never be blind-retried. This feeds the
  per-dialect retryable classifier research.md §5 delta 5 already
  proposes, with two extensions from this pass: the classifier wraps
  **read** transactions too (JuiceFS roTxn retries reads with the
  same shouldRetry, juicefs/pkg/meta/sql.go), and a retryable outcome
  means **restart the whole protocol method from its first read**,
  never retry-the-statement — FreeBSD threads ERELOOKUP through every
  namespace op and restarts the entire syscall from lookup
  (freebsd-src/sys/ufs/ffs/ffs_softdep.c:3218-3289;
  sys/kern/vfs_syscalls.c:3791, 3841-3862).
- **Arbitration latency is bounded by the rival's transaction
  lifetime** on Postgres (the loser blocks under SnapshotDirty until
  the rival commits or aborts, nbtinsert.c:563-601) — lock_timeout is
  the tunable, a distinct axis from SQLite busy_timeout.
- **If vfs ever grows a lock-like feature** (if_revision holds,
  exclusive sessions), spec lease/timeout semantics from day one:
  fossil's DMEXCL exclusive-open needed a 5-minute renewed lease
  because server-side exclusivity without expiry deadlocks on dead
  clients (plan9/sys/src/cmd/fossil/9excl.c:21-95).

## W8 — Durability and crash consistency: settled-with-amendments

**Resolution: settled-with-amendments.** The window inventory is
complete and short — but the spec's implicit premise that the §6 index
epoch is the *only* declared window is **false as written**, and
"committed" needs a definition.

**The contradiction.** At SQLite's common WAL pairing
`synchronous=NORMAL`, "transaction commit is not synced"
(sqlite/src/pager.c:607-618; walFrames pads and syncs the commit frame
only at FULL, sqlite/src/wal.c:4175-4211): a committed op is atomic,
ordered, and immediately visible (the wal-index header publishes
before commit returns, wal.c:4243-4256) but **not power-loss durable
until the next checkpoint sync**. The same acknowledged-vs-durable gap
is the norm across the lineage: jbd2's journal_stop returns without
waiting for commit (linux/fs/jbd2/transaction.c:1883-2012); git's
default fsync mask excludes loose objects and refs entirely
(git/write-or-die.h:27-38); Postgres makes it an explicit
per-transaction tier (`synchronous_commit`,
postgres/src/include/access/xact.h:69-81) — the shipped precedent for
*declaring* durability rather than assuming it. The adversarial
capstone: fossil parses 9P's explicit flush-to-stable-storage request
and silently no-ops it (plan9/sys/src/cmd/fossil/9p.c:364-371) — a
protocol can define the durability verb and a mature server can ship
it dead for years, so the promise must be pinned by configuration and
test, never inferred from the interface.

**Resolution:** the SQLite backend pins `synchronous=FULL` at first
touch (one WAL fsync per commit — the right default for agents doing
read→edit→write cycles), or else the NORMAL-mode window is a second
declared eventual-consistency instance alongside the §6 staleness
window. Either way, §10 gains a sentence defining "committed" per
engine — atomic (recovery truncates at the last valid commit frame,
sqlite/src/wal.c:1495-1518), immediately visible, durable per the
declared tier — surfaced as a capability trait. Conformance tests
asserting durability-after-crash pin the tier explicitly; under async
commit a lost-but-acknowledged transaction is not a backend bug
(postgres/src/backend/access/transam/xact.c:1515-1574).

**The window inventory** (the question's second half):

1. **Within one transaction: zero windows.** The substrate closes
   ext4's four machinery-windows by construction — torn-transaction
   replay (strict prefix, discard the suffix), metadata-before-data
   ordering, block-reuse revocation, commit-vs-checkpoint — one
   commit frame, all-or-nothing recovery
   (linux/fs/jbd2/recovery.c:~640-700; commit.c:571-577;
   revoke.c:12-45; sqlite/src/wal.c:4129-4256). Postgres identically:
   heap + TOAST + index rows share one commit record
   (postgres/src/backend/access/transam/xact.c:1540-1574).
2. **Between transactions — the multi-transaction seams vfs itself
   creates**, which reproduce exactly the window the ext4 orphan list
   was built for (linux/fs/ext4/orphan.c:89-100): (a) crash mid-epoch
   build leaves epoch-N+1 posting rows nobody references; (b) crash
   after the flip, before old-epoch reclamation, leaves epoch-N
   garbage; (c) trash rows past retention, pre-sweep (W6). All three
   are reader-invisible (epoch filter / trash-prefix filter) but are
   storage leaks — the duty is orphan-list-shaped: durable rows *are*
   the queue, and every sweep (reindex reclamation, trash sweep) is
   idempotent and resumable at any crash point, removing all rows of
   any epoch other than current (the ext4_orphan_cleanup analogue).
   LFS's roll-forward rule is the recovery doctrine: derived state
   that outran its authority row is discarded, never trusted
   (Rosenblum & Ousterhout, TOCS 1992, §4.2).
3. **The ack-vs-durable gap** — configured away (`synchronous=FULL` /
   `synchronous_commit=on`) or declared, per the resolution above.

Classification discipline (literature): every window is tagged
**stale-declared** (the §6 watermark + dirty overlay) or **leak with
a named sweeper**; the **corrupt** class must be empty — that
assertion makes §10's "no split-brain surface beyond that declared
window" checkable instead of asserted (Ganger & Patt, OSDI '94, §7 —
soft updates' shipped doctrine is benign declared inconsistency plus
an owned asynchronous repair path). The FFS mount-policy split feeds
first-touch: benign declared staleness → serve and surface;
unknown/incompatible state (schema-version mismatch) → refuse loudly
(freebsd-src/sys/ufs/ffs/ffs_vfsops.c:928-953), fusing with
research.md §5 delta 4's schema-version row.

## Recommended spec deltas (actionable)

1. **§5 (W2):** resolve the encoding sentence — 64-bit integer
   counter, backend-owned, stamped in the same transaction as the
   material write, incremented unconditionally (no lazy-increment
   complexity — vfs lacks the journaling pressure that motivated it).
   Define "material write" to include metadata-only mutations
   (RFC 7862 §10); add the parent-directory bump on namespace
   mutations (iversion contract + ext4 + fossil); state the
   never-observable-early ordering sentence; declare the encoding as
   a capability trait (`change_attr_type` precedent). Amend
   research.md §"§5 revision": strike "No filesystem precedent
   exists" → "no precedent in the nine repos; the protocol layer
   (i_version, qid.vers, NFSv4 change attribute) is the standing
   precedent and it prefers counters."
2. **§9 (W6a):** replace the soft-delete open question with
   trash-reparent — same-transaction reparent into time-bucketed
   trash nodes under the meta namespace; restore metadata as row
   columns (never name-encoded); restore = move-no-replace with
   exists → conflict; re-scope the chokepoint sentence from
   "IS NULL predicate" to "meta/trash namespace-prefix exclusion";
   add the reclamation sweep verb (idempotent, grace-windowed,
   deletes bucket subtrees + orphaned version/chunk/gram rows,
   caller-scheduled).
3. **§10 (W6b):** add the cross-directory-move paragraph — cycle
   refusal executes under the serialization that freezes topology;
   SQLite's single writer suffices; Postgres declares its mechanism
   (advisory lock / SERIALIZABLE move / commit-time re-check). Add
   the move contract sentence (no observable no-name, both-names, or
   partial-subtree state). Strengthen the §9/§12 cycle criterion with
   the concurrent two-move test on two instances, one database.
4. **§10 (W7):** the SQLite lock-discipline paragraph states the
   mechanism — busy_timeout is only consulted with no open
   transaction; writes open BEGIN IMMEDIATE; BUSY_SNAPSHOT is a
   discipline violation classified loudly; no COMMIT-retry provision
   exists. The retryable classifier splits 40001 (retry whole op,
   from the first read — ERELOOKUP shape) from 23505 (definite
   exists); wraps read transactions too. Add: the revision guard
   appears in the WHERE of every material write (EvalPlanQual
   silent-lost-update hazard).
5. **§10 (W8):** define "committed" per engine and pin
   `synchronous=FULL` on SQLite at first touch (or declare the NORMAL
   window as a trait); add the window inventory with the
   stale-declared / leak-with-sweeper / corrupt-empty classification;
   extend "the §6 gram index is the one declared instance" to name
   reclamation windows generally (index epochs, trash retention).
   First-touch splits benign staleness (serve) from schema mismatch
   (refuse), fusing with the schema-version row (research.md §5
   delta 4).
6. **§3 (W1/W5):** add — statement order inside the transaction
   carries no crash-consistency weight but is load-bearing for
   constraint timing; pin a canonical order (parents before children,
   entries before versions/edges). Internal helpers never open/commit
   transactions. The one-commit guarantee holds only while content
   stays in the transactional store — moving it out is a design fork,
   not an optimization. A batch is ONE transaction even when
   statements chunk by parameter budget; per-entry outcomes are
   classified, never silently skipped. Restate the acceptance
   criterion: O(tables touched) statements per parameter-budget
   chunk, budget declared per dialect.
7. **§3/§9 (W4):** direct the content layout — content in its own
   node_id-keyed table, one blob per row, blob column last; entries
   row stays narrow so revision stamps never rewrite content
   (overflow-chain hazard + TOAST pointer-reuse precedent); id-keyed
   chunk rows are the recorded fallback; `sqlite3_blob_*` recorded as
   future-streaming escape hatch only.
8. **§9 (W3):** keep forward diffs + snapshot-every-10 as v1 default;
   record why (COW's 4–6× write load + refcount GC; git's depth-50
   tolerance) and the write-path read amplification it costs; verify
   content hash on write and read; hash mismatch classifies as a
   dedicated corruption kind naming version and chain position;
   note the snapshot corruption-firewall property; the precedented
   fallback if the spike fails is store-full + batch delta (git
   shape), never deeper intervals.
9. **§12:** harness rows from this pass — trashed path → not_found
   through every read verb; op under deleted ancestor → not_found;
   crash-simulated delete leaves row families consistent; move
   refusal order (source-missing > target-exists > cycle >
   permission) and the cycle-direction kinds pinned; two-writer
   concurrent-create and concurrent-move tests; WAL file returns to
   baseline after an op storm (no session held across ops).

## What only the spike can answer

> **Answered 2026-07-13** — see `spike-results-pipelines.md`.
> Headlines: snapshot-every-10 validated (worst replay 5.2 ms at
> 256 KB; the write-side diff costs more than the read replay);
> inline-content metadata bump measured at 259× WAL amplification —
> separate content table confirmed, `page_size=16384` adopted; batch
> criterion is a wire-dialect rule (in-process SQLite indifferent);
> BEGIN IMMEDIATE ran 600 contended ops with zero errors and the
> **move-cycle composition was observed at READ COMMITTED and
> REPEATABLE READ** (advisory lock recommended); `synchronous=FULL`
> costs 2× and clears 6,500 commits/s — pinned.

1. **Version-chain reconstruction latency** (W3): Python
   unified-diff apply throughput; reconstruction latency vs chain
   length × snapshot interval across the doc-size distribution. The
   chain *shape* is settled; this validates (or re-tunes) the
   constant 10. Includes the write-side number: create_version's
   read-previous-content cost inside the write transaction.
2. **Content-layout cliff** (W4): separate-table blob vs id-keyed
   chunk rows vs threshold hybrid (TOAST's ~2 KB shape) across the
   495K-doc corpus tooling; SQLite `page_size` 8192/16384 on the
   content table (the local/spill threshold scales with usableSize,
   sqlite/src/btree.c:3447-3450) — the cheapest write-amplification
   lever available.
3. **Batch write** (W5): statement count and wall-clock at 1K
   entries under the per-dialect parameter budgets, SQLite and
   Postgres — pins the restated criterion's constants.
4. **Two-writer SQLite contention** (W7): BEGIN IMMEDIATE vs
   deferred × busy_timeout on two instances, one database —
   confirms BUSY_SNAPSHOT is unreachable under the discipline and
   measures arbitration latency; plus the concurrent-move cycle
   composition probe on Postgres at READ COMMITTED (does the
   in-snapshot ancestry check actually admit a cycle, and which
   declared mechanism closes it cheapest).
5. **Durability pricing** (W8): `synchronous=FULL` vs `NORMAL`
   commit latency under the write-op mix — prices the pinned
   default so the trait choice is measured, not asserted.
