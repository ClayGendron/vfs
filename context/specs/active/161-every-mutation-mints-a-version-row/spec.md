# 161 — Every mutation mints a version row: the undo the README promises

- **Status:** seed — cut 2026-10-08 from the SmartOwl integration memo;
  revised 2026-10-08 after a review against `0760fe9` (the versions
  table's real columns, the snapshot cut ADR 017 already fixed, the
  dormant diff provider, the label semantics, the paging claim, the
  missing `read(version=)`); needs its own research pass and an ADR
  before it is shaped
- **Date:** 2026-10-08
- **Owner:** Clay Gendron
- **Kind:** feature (a read-side verb or parameter for history; version
  retention; the mint itself lands in spec 162 slice B)
- **Bound by:** ADR 074 item 5 — spec 162 slice B lands the write-replace
  mint (`versions.py` beside `writes.py`), which a live overwrite and a
  revive of a tombstoned row share. This spec owns the read side and
  retention, and the ADR that ratifies both.
- **Depends on:** ADR 017 (version numbers are revision values; pin 4:
  "the write path itself always snapshots", diffs belong to a later
  pack verb; pin 2: no `action` field), ADR 064 (every version row
  names actor and subjects), 152 §3 (bytes versions are full snapshots
  in `vfs_versions.data`), the `vfs_versions` table (`models/rows.py`
  L515–536) and its side table `vfs_version_subjects` (L541–548), the
  trash purge in `topology.py` L713–715 (the only code that touches
  version rows today), `Authority` (`authority.py` L124–128: actor,
  subjects, provenance, source_identity) and `read_revision`
  (`revision.py` L46–60, which `writes.py` does not call today).
- **Research it stands on:**
  `../../../research/2026-10-08-smartowl-workspace-integration-issues.md`
  item 1. The cut is decided: the write path mints full snapshots
  (ADR 017 pin 4; 152 §3 for bytes). `models/versioning.py` (forward
  unified diffs, `SNAPSHOT_INTERVAL = 10`, `unidiff` as a core
  dependency) and `Version.create`'s diff arm (`models/version.py`
  L112–155) are called nowhere outside `models/`; they are the pack
  verb's, and the research pass decides whether they stay dormant or
  are retired with `unidiff`. Still owed to the pass: the read-side
  shape, retention, and the ADR 017 amendment below.

## Intent

The README says a mutation is "versioned, reversible" and "can be
undone" (L55, L87). The table, the side table and the attribution
columns exist, and no write path writes to them: `write` and `edit`
replace the body in place, so an overwrite is gone. Delete is the only
reversible mutation, through the trash. 153 softens the README until
this lands; 162 slice B lands the mint; this spec lands the way to
read what it minted.

One line: a write or edit that replaces a body first saves the body it
replaced, with the actor, and a reader can get it back.

## Seed semantics (to be ratified by an ADR)

1. **`write` and `edit` of an existing body — a live overwrite or a
   revive of a tombstoned row — mint one version row** in the same
   transaction as the replacement, carrying the replaced body
   (`content`, or `data` per 152 §3) as a snapshot (`is_snapshot =
   true`, `version_diff` null), the replaced `version` as
   `version_number`, its `content_hash`, `size_bytes` and `lines`, the
   attribution columns of ADR 064 — `actor`, `provenance`,
   `source_identity`, `grant_revision` (one `read_revision` per write
   transaction) — one `vfs_version_subjects` row per subject, and
   `created_at`. No op or action is recorded (ADR 017 pin 2). A create
   mints nothing; a delete keeps the row as a tombstone (ADR 074) and
   mints nothing; a revive of a bodiless row (a directory) mints
   nothing.
2. **The label is the replaced row's version.** After write then
   write, `stat` reports `version == 2` and the row holds
   `version_number == 1`: row N is the body at version N. The current
   body is served from the live row, never from `vfs_versions`; a
   never-overwritten file has no history rows. ADR 017 pin 1 ("a
   version row's label always equals a stat's revision immediately
   after the write") is amended by the ADR this seed owes.
3. **A bulk write mints in bulk.** A 10,000-file batch that replaces
   10,000 bodies inserts its version rows through `bulk_insert` paged
   by `rows_per_statement`, and its subject rows likewise; no per-row
   statement. A version row has fourteen columns where a content row
   has three, so the page is smaller on parameter-bound engines (about
   150 rows a statement on SQL Server against about 700): the count is
   bounded per dialect, never per row.
4. **History is readable.** `read` has no `version=` today
   (`base.py` L858–865). ADR 064 rule 6 already answers the rollback
   half: a rollback is a `write` of the old content under current
   grants, minting its own row.
   `[NEEDS CLARIFICATION: a `versions` read verb, a `version=`
   parameter on `read`, or both? Owed to the research pass; `restore`
   does not grow a `version=` form, per ADR 064 rule 6.]`
5. **Retention is a storage setting** like `trash_days`
   (`backend.py` L186–220, `memory.py` L47). The sweep that purges
   trash runs a sibling chunked `DELETE … WHERE created_at < cutoff`
   on both version tables in the same pass. Snapshot-only rows make
   age-based deletion safe; a diff chain would not be.

## Scope (once shaped)

- The read-side verb or parameter and its projection.
- The retention setting and the sweep arm.
- The ADR: ratify items 1–5, amend ADR 017 pin 1, decide the fate of
  `models/versioning.py` and `unidiff`.
- Tests that count version rows and statements per batch, and a
  `python -O` parity check that nothing load-bearing is an `assert`.
- Out of scope: the mint (162 slice B), diffs for text (snapshot
  first; a pack verb is a later spec), edge versions.

## Acceptance criteria (draft)

- After `write` then `write` to one path, `stat` reports `version ==
  2`; `vfs_versions` holds one row with `version_number == 1`, whose
  `content` is the first body and whose `actor` is the writer; the
  history form the research pass picks returns it.
- A 10,000-file overwrite batch mints with a statement count bounded
  by `ceil(N / rows_per_statement(budget, version_row))` plus the
  subject pages and the byte-paged blob pages; the test counts
  statements.
- 153's softened README sentences (L55, L87) come back in the landing
  commit of the read-side verb, not of the mint.
