# 074 — plan

Approach: rewrite revision mechanics in place, schema first (so the
drift test drives the rest), then the database write path, then the
memory mirror, then traits and tests. Every step leaves the tree green.

## 1. Schema and provisioning

- `rows.py`: drop `revision_counter` from `meta` (and its docstring
  paragraph — the "regressed counter" rationale is superseded by
  ADR 013); drop `watermark` from `gram_epochs` (fingerprint = format
  version + options hash); add `Column("encoded", Boolean,
  nullable=False, default=False)` to `chunks`.
- `engine.py:267`: first-touch meta insert loses `revision_counter=0`.
- `tests/test_rows.py:153` (gram_epochs column set) and `:253`
  (meta insert shape) update with the schema.

## 2. Database write path (`writes.py`)

- Delete `allocate_revisions` and the "Revision allocation" section.
- `_Staged.revision` becomes derived, not range-assigned: creates
  stage `revision = 1`; guarded updates stage `revision =
  base_revision + 1` at `stage_update` time (base is already read).
  The clobber arm (`base_revision is None`) stages no value — its
  UPDATE sets `revision = entry.c.revision + 1` SQL-side.
- `_apply`: the allocation preamble (`high`, `values`, per-staged
  assignment, `bump_revisions` pre-assignment) goes away. Bumps become
  one `UPDATE entry SET revision = revision + 1 WHERE id IN
  (:bump_ids)` — no executemany, no pre-assigned values.
- `_update_materials`: guarded arm unchanged except values come from
  the staged base+1; unguarded arm moves the increment into the SET
  clause. The read-back select already runs and stamps clobber rows'
  observed revisions. Vanished ids still classify `conflict`; a
  guarded row whose read-back value ≠ base+1 still classifies
  `conflict`. Unguarded rows take the read-back value as truth
  (last-writer-wins by design). Bump values CANNOT ride this select —
  it runs before the bump statement in the pinned order; they need
  their own conditional read-back after the bump (corrected during
  implementation: all three candidate implementations independently
  flagged the original wording here as unexecutable).
- `_upsert_layer`: clobber `set_` adds `revision: entry.c.revision + 1`
  (target-row reference, valid in `ON CONFLICT DO UPDATE` on both
  sqlite and postgresql dialects) and drops `revision` from
  `_CLOBBER_COLUMNS`' excluded-column treatment; extend RETURNING with
  `entry.c.revision` so clobber winners learn their value without the
  read-back where possible.
- `_finish`: `plan.bump_revisions` now populated from the read-back
  (or empty when no observation needs it) — the "unchanged row
  reports the bump" behavior is preserved, sourced differently.

## 3. Memory backend (`memory.py`)

- Delete `_next_revision` and the `_revision` counter. Creates (write,
  mkdir, mint_chain, mkedge, copy-minted rows) get `revision=1`;
  mutations and bumps get `row.revision + 1`; move keeps descendant
  revisions (already the case).

## 4. Traits and protocol

- `protocol.py:83`: `frozenset({"counter64"})` → `frozenset({"per_entry64"})`.
- `backend.py` and `memory.py` `traits()` return the new value.

## 5. Tests

- Replace the counter tests (`tests/test_backends_database.py:792`
  region, `test_revision_counter_survives_restart:827`) with per-entry
  semantics tests: create=1, +1 on overwrite/edit, bump composition,
  stat agreement.
- Conformance suite: audit for cross-entry revision-ordering
  assertions; rewrite to per-entry monotonicity.
- New statement-count fixture: `before_cursor_execute` listener on the
  sync engine under the async adapter; pin create=5 / overwrite=5.
- Guarded-conflict tests keep their behavior; only expected revision
  *values* change.

## 6. Docs residue

- Root `write-pipeline.md`: update the diagram (allocation node goes;
  bump becomes SQL-side increment).
- `writes.py` module docstring: revision sentence rewritten
  (per-entry, no counter).

Trade-offs called: SQL-side increment for bumps/clobbers costs nothing
extra (the read-back already exists) and composes under concurrency,
where client-side `old+1` would lose increments at READ COMMITTED.
Statement counts: create 7→5, overwrite 7→5; further trims
(content upsert) stay out of scope per the spec.
