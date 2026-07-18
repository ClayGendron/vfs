# 074 — Per-entry revisions: drop the ordered per-mount counter

- **Status:** shaped — drafted 2026-07-17 directly from accepted ADR 013;
  no open markers. Ready for plan.md.
- **Date:** 2026-07-17
- **Owner:** Clay Gendron
- **Kind:** contract + schema change (revision semantics on every
  mutation verb; `meta`/`gram_epochs`/`chunks` columns; one trait value)
- **Depends on:** ADR 013 (binding), 072 (the landed write pipeline this
  rewrites in place)
- **Relates to:** the future grep/reindex pass (consumes the
  flag-partitioned overlay this spec's schema prepares), the future
  staged-content spec (memo §4.4), the storage conformance suite (pins
  the semantics both backends must match)

## Intent

Every write batch today claims an ordered range from the per-mount
`revision_counter` row and holds that row's lock to commit
(`writes.py` `allocate_revisions`). ADR 013 found the ordering serves
only the never-built index watermark, and that on Postgres the counter
row is a global mutex collapsing per-mount write concurrency to ~1.
This spec executes ADR 013 pins 1–3 and the trait rename against the
live tree: revisions become per-entry monotone values, ordered
allocation and its schema leave the system, and the index-status flags
become the (future) grep overlay's dirty set.

One sentence: **a revision names "which version of this entry", never
"which write on this mount" — no two entries' revisions are comparable,
and no write waits on any row it isn't mutating.**

## Shape (pinned)

1. **Creation mints revision 1.** Every freshly created row — file,
   directory, minted ancestor — carries `revision = 1`.
2. **Material updates increment by exactly one, guarded.** The guarded
   arm writes `revision = base + 1` with `WHERE revision = base` — the
   guard survives unchanged as the portable lost-update defense, and the
   post-execution read-back verifies the expected value exactly as
   today. The arbitration-clobber arm (rival's row absorbs our write)
   increments SQL-side (`revision = revision + 1`) since no base is
   known; it stays unguarded and last-writer-wins by design, with the
   read-back supplying the observed value and still catching vanished
   rows as `conflict`.
3. **Parent bumps increment SQL-side, unconditionally.** One
   `UPDATE ... SET revision = revision + 1 WHERE id IN (...)` — no
   pre-assigned values, so concurrent bumps of the same directory
   compose instead of overwriting each other. Bumped values are read
   back only when an observation needs one (an "unchanged" pending row
   whose parent-bump must equal a post-commit stat). Synchronous bumps
   are the ADR's accepted near-term shape; their removal
   (derive-from-children) is a future spec.
4. **Observations still equal a post-commit stat.** The invariant is
   unchanged; only the source of values moves (client-assigned range →
   base+1 arithmetic and read-backs).
5. **Ordered allocation leaves code and schema.** `allocate_revisions`
   is deleted; `meta.revision_counter` is dropped (first-touch in
   `engine.py` stops provisioning it); `gram_epochs.watermark` is
   dropped — the epoch fingerprint keeps format-version and
   options-hash only, per ADR 013 pin 3. Greenfield: no migration.
6. **Chunks carry their index-status flag.** `chunks` gains
   `encoded` (Boolean, not-null, default false) — the per-chunk dirty
   flag ADR 013 pin 3 commits to. Embedding staleness needs no flag
   (`embedding IS NULL` already encodes it). No consumer in this spec;
   the schema lands so the reindex pass builds on it, and the drift
   test tracks it.
7. **The trait renames.** `revision_encoding: "counter64"` →
   `"per_entry64"` in `protocol.py`'s declared values and both
   backends' `traits()`. The name states the new contract: 64-bit,
   monotone per entry, incomparable across entries.
8. **The memory backend mirrors exactly.** Its global `_next_revision`
   counter is replaced by the same semantics — create = 1, mutate =
   +1, bump = +1, copy mints fresh rows at 1, move keeps descendants'
   revisions. Backends stay observationally interchangeable; the
   conformance suite asserts the shared semantics, and any existing
   assertion of cross-entry ordering is rewritten to per-entry.

## Acceptance criteria

- `allocate_revisions` and `revision_counter` appear nowhere in `src/`
  or `tests/`; `gram_epochs` has no `watermark` column; `chunks` has
  `encoded`.
- On both backends: a created entry observes `revision == 1`; an
  overwrite and an edit each observe exactly `+1` and a subsequent
  `stat` agrees; a `mkdir exist_ok` observation of a bumped directory
  equals its post-commit stat.
- Two same-target writers under the database backend: exactly one
  succeeds and the loser classifies `conflict` — the guard's behavior
  is unchanged (existing concurrency tests pass with revised
  expectations only where they asserted mount-ordered values).
- A statement-count fixture (SQLAlchemy `before_cursor_execute`
  listener) pins the single-file-create batch at **5 statements**
  (fetch, insert, content delete+insert, bump) and the overwrite batch
  at **5** (fetch, guarded update, read-back, content delete+insert) —
  the round-trip budget becomes a regression guard, not folklore.
- `traits()["revision_encoding"] == "per_entry64"` on both backends;
  the protocol's declared trait values updated in lockstep.
- Full suite green; `ruff` and `ty` at zero across `src/` and `tests/`;
  the `rows.py` drift test reflects the schema deltas.

## Out of scope

- Removing parent bumps (derive-from-children) — future spec under
  ADR 013 pin 5.
- Staged-then-publish content for large writes (memo §4.4) — future
  spec.
- Grep/reindex flag consumers — the future grep pass; this spec only
  lands the schema and semantics they build on.
- Unifying `versions.version_number` with `revision` — noted as a
  possible future alignment, deliberately untouched here.

Evidence: `decisions/013-per-entry-revisions.md`;
`research/2026-07-17-write-path-prior-art-and-scaling.md` §§3–4.
