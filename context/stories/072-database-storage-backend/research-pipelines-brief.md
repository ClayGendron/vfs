# 072 research brief — read and write pipelines, from source

- **Date:** 2026-07-13
- **Status:** brief — Phase 0 of the pipelines research; grounding
  document for every researcher in Phases 1–3
- **Owner:** Clay Gendron
- **Deliverables:** `research-write-pipeline.md` and
  `research-read-pipeline.md` (two docs, per owner decision
  2026-07-13), then `spike-results-pipelines.md` + `spike/` additions
  for whatever only measurement can answer, then spec.md §§2, 3, 5, 9,
  10 resolved the way §6 was (dated resolution, struck-through open
  question, pointer to evidence).
- **Method:** the `research.md` / `research-grep-index.md` protocol —
  parallel researchers over local checkouts, each grading every
  question **supports / contradicts / nuanced / no-precedent** with
  file:line evidence, instructed adversarially (contradictions valued
  over agreement), extrapolations flagged, followed by an independent
  refutation pass on every load-bearing claim.

## Confirmed premises (inputs, not questions)

1. **Identity option (c) is confirmed** (owner, 2026-07-13; spec.md §4):
   `node_id` ULID, `parent_id`, ID-keyed edges, materialized path as
   regenerable cache. 059 lands as the binding ADR before plan.md.
   Researchers treat the (c) schema as the given substrate.
2. **Revision ships in Pass A** (spec.md §5, doubly mandated by the §6
   index watermark). The open question is *encoding and semantics*, not
   whether.
3. The nine-repo findings in `research.md` and the grep deep-dive in
   `research-grep-index.md` are standing evidence — do not re-derive
   them; cite them, extend them, or contradict them with new evidence.

## Reference roster (local checkouts under `~/Git/Repos/`)

| researcher | checkout(s) | why it is on the roster |
|---|---|---|
| linux-vfs | `linux` | `fs/namei.c` path-walk + error precedence, dcache/negative dentries, `lock_rename`/`s_vfs_rename_mutex` ordering, `statx` field masks, `i_version` change attribute |
| linux-journal | `linux` (`fs/ext4`, `fs/jbd2`, `fs/btrfs`) | journaling modes (`data=ordered`), orphan inode list, what commit promises; btrfs COW transaction groups + snapshots as the in-tree COW counterpoint |
| plan9 | `plan9`, `plan9port` | 9P fid/qid model, `qid.vers` per-write increment, `wstat`, fossil append + venti content-addressed snapshots, everything-through-one-message-vocabulary |
| unix-history | `unix-history-repo`, `freebsd-src` | V7 inode indirection and namei origins; FFS/UFS soft-updates dependency-ordering rules, fsck-as-repair, rename atomicity lineage |
| sqlite | `sqlite` | the substrate: pager/WAL commit semantics, snapshot-at-first-read, `BEGIN IMMEDIATE`, busy handling, overflow pages, incremental blob I/O |
| postgres | `postgres` | MVCC/heap visibility, WAL, what a reader sees mid-write, TOAST as a content-layout precedent |
| git | `git` (shallow-clone before Phase 1) | content-addressed object store, packfile deltas vs loose objects, the index as a staging structure — the strongest versioning counterpoint to forward-diff chains |
| literature (web) | — | canonical papers only where code can't answer: soft updates (Ganger/Patt), LFS, WAFL, NFSv4 change attribute, "The Use of Name Spaces in Plan 9"; every claim cited to paper §page |

Prior-roster repos (juicefs, agentfs, libsqlfs, seaweedfs, opendal,
fsspec, pyfilesystem2, pjdfstest, zoekt) are consulted via
`research.md`, not re-reviewed.

## Question inventory — write pipeline (`research-write-pipeline.md`)

- **W1 — Transaction shape and ordering** (spec §3, §10). One session
  per op; entry row + version row + content in one commit. What
  ordering invariants do journaling/soft-updates systems enforce
  between metadata and data, and which of them does a SQL transaction
  give us for free vs which must be designed (e.g. cross-table
  ordering inside the txn)? What exactly does "committed" promise?
- **W2 — Revision encoding and semantics** (spec §5). Counter vs
  `updated_at‖hash`. Precedents to weigh: Linux `i_version` (including
  its lazy-increment optimization and the NFSv4 change-attribute
  contract), 9P `qid.vers`, SQLite `data_version`. Note: `research.md`
  §"§5 revision" claimed *no filesystem precedent* — this inventory
  expects that claim to be overturned at the protocol layer; grade it.
- **W3 — Version chain design** (spec §9). `versioning.py` forward
  diffs + snapshot-every-10 vs content-addressed (venti, git objects/
  packs) vs COW (btrfs). Reconstruction cost model, integrity (hash
  verification on reconstruct), dedup, and GC of unreachable versions.
  Is snapshot-every-10 defensible or a spike question?
- **W4 — Content layout** (spec §3, §9). Single inline blob column vs
  block/chunk rows (the libsqlfs 8K-block scar) vs TOAST-style
  out-of-line. SQLite overflow-page behavior, incremental blob I/O,
  write amplification per layout. Where is the size cliff, if any?
- **W5 — Batch write discipline** (spec §3, acceptance criteria).
  Constant statement count for N-entry batches, parameter budgets,
  partial-batch classification, all-or-nothing vs per-entry outcomes.
- **W6 — Rename/move/delete atomicity and the delete model** (spec §9,
  §10). POSIX rename guarantees; Linux `lock_rename` ordering and
  cycle refusal at depth; ext4 orphan-inode handling for crash-window
  deletes; JuiceFS trash-reparent vs `deleted_at` chokepoint vs
  hard-delete + version history. **This question resolves the §9
  soft-delete marker** — researchers must land a recommendation, with
  the reclamation/GC story (research.md gap #4) in scope.
- **W7 — Concurrent writers and arbitration** (spec §10). Unique-index
  arbitration vs lock-based; retryable-error classification;
  SQLite single-writer discipline (`BEGIN IMMEDIATE`, `busy_timeout`,
  WAL, pool-of-one); Postgres MVCC conflict shapes; where in-process
  throttles are throughput aids vs correctness hazards.
- **W8 — Durability and crash consistency** (spec §10). What the
  substrate's commit already promises (SQLite WAL, Postgres WAL) and
  what remains for the backend to promise or *declare* (the §6 index
  epoch is the one declared eventual-consistency window — is it the
  only one?). Crash between entry txn and any derived row: enumerate
  the windows.

## Question inventory — read pipeline (`research-read-pipeline.md`)

- **R1 — Path resolution** (spec §4-adjacent, §12). Full-path unique
  key + `parent_id` walk + materialized path cache (the (c) substrate)
  vs component-walk. dcache lessons: negative dentries (caching
  not-found), RCU-walk's read-without-locks discipline, when a
  resolution cache is safe without invalidation protocol. AgentFS's
  hand-invalidated dentry cache is the standing scar.
- **R2 — Stat and projection push-down** (spec §3). `statx`'s
  per-field request mask as the precedent for the `columns`
  projection; cheap-vs-expensive field tiers; the loud not-loaded
  signal (projected-out ≠ null) at the Observation layer.
- **R3 — Directory listing: order and pagination** (research.md gaps
  #2, #3). Binary-collation ordering pinned in DDL; `getdents`
  cookies / NFS readdir cookies / `seekdir` fragility as the
  pagination precedents; listing stability under concurrent mutation;
  when materialized lists hit the cliff and what the protocol
  extension looks like (record, don't build).
- **R4 — Read consistency** (spec §10). What a reader sees relative to
  a concurrent writer: SQLite WAL snapshot-at-first-read, Postgres
  MVCC snapshots — per-op snapshot isolation is nearly free; state it
  as a contract or leave it undeclared? Read-your-writes across
  sequential ops on one backend.
- **R5 — Version and meta reads** (spec §9). Reconstruction from the
  diff chain: cost vs chain length, content-hash verification failure
  classification (what kind does a corrupt chain map to), meta-path →
  row mapping via `paths.py` decomposition.
- **R6 — In-process caching discipline** (spec §10). The 9P client
  cache model (caching needs leases/invalidation; cap), what
  state is safe to hold between ops (target: none correctness-bearing),
  and the criteria a future cache must meet (verify/repair path per
  JuiceFS `doRepair`).
- **R7 — Subtree enumeration at scale** (tree/ls -R/glob feed). Path-
  prefix `LIKE` on the path cache vs `parent_id` recursive CTE:
  when each wins; budget/truncation semantics for huge trees
  (mirroring §6's runtime-budget doctrine).
- **R8 — Error precedence along the read path** (spec §12). Pin the
  per-verb error-ordering matrix (wrong_kind ancestor vs missing leaf,
  etc.) with `fs/namei.c` and FreeBSD `namei` as the authorities —
  this feeds the conformance harness's error-ordering matrix
  (research.md §3 harness upgrade #1) with real precedent instead of
  invented order.

## Grading protocol (all researchers)

1. Read spec.md (§§2, 3, 5, 9, 10 closely), this brief, and the two
   prior research docs before opening the reference source.
2. For each question you have evidence on: verdict
   **S / C / N / no-precedent**, with file:line (or paper §) citations
   for every claim. A verdict without a citation is discarded.
3. Adversarial stance: a contradiction of the spec or of this brief's
   premises is worth more than an agreement. If the reference system
   tried our shape and retreated, the retreat is the finding.
4. Flag every extrapolation explicitly. Distinguish "the code does X"
   from "X would follow for vfs."
5. Lessons must be actionable as spec deltas: name the spec section
   and the sentence that should change.

## Verification pass (Phase 3)

Every load-bearing claim in the two synthesized docs gets an
independent skeptic that reopens the cited source and attempts to
refute the citation. Claims failing verification are cut or downgraded
to flagged extrapolation. The docs ship with nothing unverified stated
as fact.

## Expected spike candidates (Phase 4 — final list comes from the research)

- Version-chain reconstruction latency vs chain length × snapshot
  interval (validates or replaces snapshot-every-10).
- Inline blob vs block-row content layout: read/write latency and
  write amplification across doc-size distribution (reuse the 495K-doc
  corpus tooling in `spike/`).
- N-entry batch write: statement count and wall-clock at 1K entries,
  SQLite and Postgres (pins the constant-statement-count criterion).
- Two-writer contention on SQLite: `BEGIN IMMEDIATE` vs deferred ×
  busy_timeout — arbitration behavior and the Result kind SQLITE_BUSY
  classifies to.
- Subtree enumeration: path-prefix LIKE vs recursive CTE at depth ×
  width.

## Out of scope for this research

- Search ladder internals (§6 — resolved; `research-grep-index.md`).
- Graph traversal design (§7 — story 067 territory).
- Provider-native accelerations (separate provider stories).
- Row-level grants / RLS (058) and principal scoping (070).
