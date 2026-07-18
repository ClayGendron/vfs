# 013. Per-Entry Revisions: Drop the Ordered Per-Mount Counter

- **Status:** accepted
- **Date:** 2026-07-17
- **Deciders:** Clay Gendron
- **Decided by:** human (the constituent calls — per-entry versions,
  flag-based index status, `updated_at` as the change cursor, no
  background work in storage — were each made by Clay in the 2026-07-17
  write-path session; acceptance confirmed same session)

## Context

Every write batch on `DatabaseStorage` allocates revisions from the
per-mount `revision_counter` row and holds that row's lock to commit,
making commit order equal allocation order (`writes.py`
`allocate_revisions`; `rows.py` meta-table docstring). The ordering
exists for one consumer: the gram-index watermark, whose dirty overlay
(`WHERE revision > watermark`) is sound only if no transaction can
commit a revision at or below a published watermark
(`research/2026-07-13-database-storage-grep-index.md` §3).

The 2026-07-17 prior-art study
(`research/2026-07-17-write-path-prior-art-and-scaling.md`) showed this
is the single structural scaling violation in an otherwise
prior-art-conformant pipeline:

- On Postgres the counter row is a manufactured global mutex — every
  writer to a mount queues in `XactLockTableWait` behind the current
  holder, collapsing MVCC row-level parallelism to ~1 writer per mount
  and bloating the hot row (`postgres`
  `src/backend/access/heap/heapam.c:3587-3591`). On SQLite it is
  harmless only because WAL already enforces a single writer.
- No studied system allocates ordered IDs per write from shared
  transactional state: Oak's revisions need no cross-node coordination
  at all (`Revision.java:177-195`); JuiceFS batches 1024–4096 IDs per
  counter touch (`pkg/meta/base.go:1506-1557`); Postgres sequences are
  deliberately non-transactional so allocation never serializes commits
  (`src/backend/commands/sequence.c:625-679`).

Meanwhile the revision stamp serves four jobs (memo §3): the
lost-update guard in every material UPDATE, the observation snapshot
coordinate, the parent namespace-change bump, and the index watermark.
Only the watermark needs mount-wide ordering — and only at reindex
time. Jobs 1–3 need per-entry monotonicity only.

Two session decisions constrain the solution space (recorded in
`open-questions.md`, resolved 2026-07-17): the mount-wide "changed
since T" cursor is `updated_at` (no change-log table, no revived
ordered allocation), and **storage owns no background work** — anything
periodic must live in an explicit verb, never a daemon or flusher.

## Options considered

- **(a) Keep the ordered counter (status quo)** — correct on every
  dialect, zero migration; permanently caps per-mount write throughput
  at one committing writer, contradicts the cold-counter law every
  reference system obeys, and costs 2 of the 7 write round trips.
- **(b) Native sequences / identity per dialect** — removes the lock
  queue, but sequence values are cached, gapped, and
  commit-order-decoupled by design, so the watermark predicate breaks;
  restoring it needs a per-dialect fence (free on Postgres via snapshot
  horizons, absent on the generic floor). Trades one portability
  problem for another.
- **(c) Sequence + writer fence at reindex** — the evolution
  `allocate_revisions`' own docstring anticipated; portable-but-fiddly,
  and still carries mount-global allocation machinery on every write to
  serve an event (reindex) that is rare.
- **(d) Per-entry versions + explicit index-status flags** (chosen) —
  the guard/snapshot/bump jobs move to a per-row monotone version with
  zero cross-writer coordination; the watermark's job is re-expressed
  as row state (`chunked`/`encoded` flags the write path already
  stamps `False` transactionally), which needs no ordering property and
  works identically on the generic floor.
- **(e) Oak-style structured revisions (timestamp, counter, node-id)**
  — solves multi-writer ordering without coordination, but buys
  cross-node comparability this single-store backend does not need, at
  the cost of a compound revision type leaking into the protocol.

## Decision

We choose (d). Five pins:

1. **Revision is per-entry and monotone.** Creates start at
   `revision = 1`; every material update executes
   `SET revision = revision + 1` guarded by `WHERE revision = :seen`
   (the arbitration-clobber arm stays unguarded, as today). The guard
   remains mandatory in every material UPDATE — it is the only
   lost-update defense on the READ COMMITTED floor. Observations report
   the per-entry value and remain equal to a post-commit stat.
2. **Ordered allocation leaves the system.** `allocate_revisions` and
   the `revision_counter` column are removed (greenfield — no
   migration). No code may assume mount-wide comparability of two
   different entries' revisions. The `revision_encoding` trait value
   `counter64` is superseded by a value naming per-entry monotone
   semantics; the protocol's declared set updates with it.
3. **Index coverage is row state, not an ordering predicate.** The
   entry-level `chunked`/`encoded` flags (already stamped `False` in
   the same transaction as every write) are the dirty set; `chunks`
   rows carry per-chunk status flags so large files re-index only
   changed chunks. The grep overlay becomes flag-partitioned — index
   side `WHERE encoded`, scan side `WHERE NOT encoded` — mutually
   exclusive by construction. Reindex flips flags only with a
   version-guarded update (`SET encoded = true WHERE id = :id AND
   revision = :seen`), closing the writer-races-indexer window with no
   fence. The epoch fingerprint keeps its format-version and
   options-hash parts; the watermark part is superseded.
4. **`updated_at` is the mount-wide change cursor, and it is coarse.**
   Wall-clock, tie- and skew-prone: "changed since T" consumers query
   with slack and dedupe by per-entry revision. Nothing may treat it as
   a total order; any future feature needing an exact order writes its
   own ADR rather than quietly reviving ordered allocation.
5. **Storage owns no background work.** Binding beyond this decision:
   reapers, derivations, and propagation run inside explicit verbs
   (reindex/admin family) or at read time — never a daemon, thread, or
   timer owned by a backend. For the parent bump specifically: the
   synchronous bump is acceptable near-term contention; the at-scale
   path derives directory change state from children at read time via
   the `parent_id` index, and stored parent bumps leave the write path
   (executes via a future spec, not this record).

## Consequences

- **Easier:** per-mount write throughput is no longer serialized —
  writers to different entries proceed at the engine's real
  parallelism; the write path drops the two allocation round trips
  (typical batch 7 → 5 statements before further trims); the reindex
  fence problem disappears on every dialect including the generic
  floor; the write transaction's lock footprint shrinks toward
  target-rows-only, the kernel-style per-file-lock model.
- **Harder:** no mount-wide total order exists — cross-entry "which
  came first" questions are unanswerable by design, and `updated_at`
  consumers must handle slack and ties; grep's overlay and reindex
  logic change predicates (flags, not thresholds) and reindex must
  implement guarded flag-flips; the memory backend must mirror
  per-entry semantics so backends stay observationally interchangeable;
  the drift test and pressure docs tracking `revision_counter` need
  updating.
- **Committed to:** the write/edit/mkdir pipeline, reindex verb, and
  protocol traits land on per-entry revisions; the flag-partitioned
  overlay is the grep staleness contract; affirmed directions executing
  via future specs — read-time directory change derivation (parent
  bumps leave the write path) and stage-then-publish content for large
  writes (memo §4.4), both under the no-background-work pin.

Evidence: `research/2026-07-17-write-path-prior-art-and-scaling.md`
(§§1–4); `research/2026-07-13-database-storage-grep-index.md` §3;
`research/2026-07-13-database-storage-write-pipeline.md` (guard
analysis); resolved entries in `open-questions.md` (2026-07-17).
Supersedes the ordered-revision semantics assumed by the story-072
write pipeline; does not supersede any numbered ADR.
