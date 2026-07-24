# 082 — The restore verb

- **Status:** landed 2026-07-24 — executes ADR 014 pin 4 and
  ADR 026 pins 3–4; the address-form and index decisions were made
  here, everything else was pinned by the ADRs. Awaiting its
  residue-mining pass and deletion.
- **Evidence:**
  `context/decisions/014-trash-normal-fs-parity.md` (pin 4);
  `context/decisions/026-self-describing-trash-names-and-restore-contract.md`
  (pins 3–4);
  `context/research/2026-07-23-trash-prior-art-naming-and-restore.md`.
- **Depends on:** spec 081 (delete reports `trash_path`) — the
  delete → `trash_path` → restore loop is this verb's primary flow.

## Problem

Trash rows carry a full restore contract
(`original_parent_id`/`original_name`/`deleted_at`) and ADR 026 pins
how lookup and refusal must behave, but no verb consumes it: the only
way back is a hand-aimed `move`. And the lookup columns the ADR calls
"indexed" are not — `models/rows.py` declares no index over
`(original_parent_id, original_name)`, so the pinned lookup would be
a full table scan.

## Decisions this spec owns

1. **One `path` argument, two address forms.** `restore(path=...)`
   (or the standard `observations` batch; exactly-one shape rule, like
   delete). A path at or under `/.vfs/trash` names its **exact row** —
   the address the delete result hands back. Any other path is an
   **original-site address**: its parent directory resolves live (the
   shared descent ladder), and trash rows match on
   `original_parent_id == parent.entry_id AND original_name == leaf`.
   Multiple candidates disambiguate by latest `deleted_at`, ties by
   greatest entry id (ULIDs are time-ordered) — the field's universal
   answer. Restore therefore follows the *surviving parent identity*:
   a parent moved since the delete restores at its new location when
   addressed there; a parent recreated at the old path (new identity)
   matches nothing and classifies `not_found` — fail-and-keep, with
   restore-by-move as the manual override.
2. **The index.** `ix_<table>_restore (original_parent_id,
   original_name)` — a plain composite index. A partial/filtered index
   (live rows are all-NULL there) is not portable across the four
   engines; the plain shape is. ADR 026 pin 3's "indexed" claim is
   trued up by an amendment note in the ADR.
3. **Restore is the move machinery with a computed destination.**
   Destination = the original parent's *current* path + `/` +
   `original_name`. Execution reuses the landed move executor —
   reparent, descendant path-cache rewrites, unconditional clearing of
   the restore columns, version bumps on the row and both parents —
   so restore and move-out-of-trash cannot drift apart.

## Refusal ladder (per target, live, request order, serialized)

- Trash-side address missing → descent-classified miss; original-site
  address with a missing/non-directory parent component → `not_found`
  / `wrong_kind` at the failing component; no matching candidate →
  `not_found`.
- Trash-side row without restore metadata (user-authored in trash) →
  `invalid` (ADR 014 pin 4).
- Original parent id no longer resolves → `not_found`, **fail-and-
  keep**: the row stays in trash, metadata intact (a failed batch
  never commits). Parent resolves but sits in trash itself →
  `invalid` ("restore the parent first").
- Occupied destination → `exists`; `overwrite=True` takes the move
  overwrite ladder (kind mismatch `wrong_kind`, non-empty directory
  occupant `not_empty`, else the occupant purges).
- Destination or any descendant rewrite past the 1,024-byte budget →
  `unaddressable`, nothing applied.
- Any per-target error fails the batch whole; the runner never
  commits a failed result.

## Backend and router posture

- **Memory backend:** deletes are permanent (no trash), so `restore`
  classifies `unsupported` and stays out of `capabilities()` — the
  conformance restore family gates on `@needs("restore")`.
- **Router:** `restore` joins `MUTATING_OPS` (write-gated, mutation
  path resolution). The delete-style busy guard applies to the
  addressed path (a bind site at or under it refuses `busy`).
- **Known seam (recorded, not solved):** a trash-side address restores
  to a destination the router cannot pre-derive, so the busy guard
  cannot see a bind site there. Reaching it needs `overwrite=True`
  onto an *empty* bound anchor; the mounts story owns bind-site
  integrity holistically.

## Acceptance criteria

- The delete → `trash_path` → restore loop round-trips content,
  kind, and subtree; restore columns are cleared; versions bump.
- Original-site restore picks the newest of stacked same-site deletes;
  older candidates stay in trash.
- Every refusal row above is pinned; fail-and-keep is asserted (row
  still in trash with metadata after a refused restore).
- Conformance restore family enforced on sqlite and all four engine
  legs, skipped on memory; the index exists in the DDL on every leg.
- Full suite, `ruff`, `ty` at zero; 100% coverage on touched modules.

## Non-goals

- Recreate-the-parent-chain (ADR 026 records it as a possible
  additive affordance; not built here).
- The sweep verb and retention policy (blocked on the open question).
- `deleted_at`-parameterized selection of an older candidate — the
  trash-side exact address already covers "restore this one".
