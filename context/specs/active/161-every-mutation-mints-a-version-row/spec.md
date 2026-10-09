# 161 — Every mutation mints a version row: the undo the README promises

- **Status:** seed — cut 2026-10-08 from the SmartOwl integration memo;
  needs its own research pass and an ADR before it is shaped
- **Date:** 2026-10-08
- **Owner:** Clay Gendron
- **Kind:** feature (database backend writes; the `vfs_versions` table
  as built; a read-side verb or parameter for history)
- **Depends on:** ADR 017 (version numbers are revision values),
  ADR 064 (every version row names actor and subjects), 152 §3 (bytes
  versions are full snapshots; `vfs_versions.data`), the `Version`
  model (`models/version.py`) and the `vfs_versions` table
  (`models/rows.py`), the trash purge in `topology.py` (the only code
  that touches version rows today).
- **Research it stands on:**
  `../../../research/2026-10-08-smartowl-workspace-integration-issues.md`
  item 1. A research pass is still owed: how the version row is cut
  (full snapshot vs diff; 152 fixes bytes as snapshots and leaves text
  open), retention, and what the read-side verb looks like.

## Intent

The README says a mutation is "versioned, reversible" and "can be
undone". The table, the model and the attribution columns exist, and
no write path writes to them: `write` and `edit` replace the body in
place, so an overwrite is gone. Delete is the only reversible
mutation, through the trash. 153 softens the README until this lands;
this spec is the landing.

One line: a write or edit that replaces a body first saves the body it
replaced, with the actor, so `restore` has something to bring back.

## Seed semantics (to be ratified by an ADR)

> **2026-10-08:** ADR 074 (accepted) binds this spec; spec 162 slice B
> lands the mint for the write-replace path, which revive and overwrite share: a `write` at a
> tombstoned path revives the row and mints a version of the replaced body
> by the same law as any overwrite.

1. **`write` and `edit` of an existing body mint one version row** in
   the same transaction as the replacement, carrying the prior body
   (text, or bytes per 152 §3), the prior `version` value, the actor
   and subjects per ADR 064, and the op that replaced it. A create
   mints nothing; a delete already keeps the row in trash and mints
   nothing new.
2. **A bulk write mints in bulk.** A 10,000-file batch that replaces
   10,000 bodies inserts 10,000 version rows through the same paged
   bulk insert the body takes; no per-row statement.
3. **History is readable.** `[NEEDS CLARIFICATION: a `versions` read
   verb, a `version=` parameter on `read`, or both? And does `restore`
   grow a `version=` form to roll a body back, or is that a new verb?
   Owed to the research pass.]`
4. **Retention is a storage setting** like `trash_days`; the sweep that
   purges trash purges expired versions in the same pass.

## Scope (once shaped)

- The mint in `writes.py`'s replace path; the bulk shape.
- The read-side verb or parameter and its projection.
- The retention sweep.
- Tests that count version rows per batch, and a `python -O` parity
  check that nothing load-bearing is an `assert`.
- Out of scope: diffs for text (snapshot first; a diff form is a later
  optimization the research pass sizes), edge versions.

## Acceptance criteria (draft)

- After `write` then `write` to one path, `vfs_versions` holds one row
  with the first body and the actor.
- A 10,000-file overwrite batch issues version inserts in the same
  number of pages as the body inserts.
- `read(path, version=1)` returns the first body.
- 153's softened README sentence comes back in the landing commit.
