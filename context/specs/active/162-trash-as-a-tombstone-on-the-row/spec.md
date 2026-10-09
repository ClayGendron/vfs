# 162 — Trash as a tombstone on the row: delete flags, restore clears, a write revives

- **Status:** draft — cut 2026-10-08 from ADR 074 (accepted the same
  day) and the memo it stands on
- **Date:** 2026-10-08
- **Owner:** Clay Gendron
- **Kind:** feature and removal (database backend: `topology.py`'s
  delete, restore and sweep arms rewritten; two row columns added,
  three removed; the trashed predicate forms removed from the rights
  algebra; the trash served as a view; the write pipeline's revive;
  the first landing of the version mint)
- **Depends on:** ADR 074; ADR 064 (every version row names actor and
  subjects, the columns the mint fills); ADR 072 and 073 as built
  (`ranges.py`, `rights.py`, `labels.py`); the write pipeline's
  occupant branch (`writes.py`); `liveness_filters` (`descent.py`);
  the purge arm (`topology.py`); spec 152 §3 (bytes versions are
  snapshots).
- **Decisions it implements:** ADR 074, all ten items. Retires the
  trashed forms spec 150 §8 built; dissolves spec 156 rule 2; lands
  the write-replace half of spec 161's mint (161 keeps the read-side
  verb and retention).
- **Research it stands on:**
  `../../../research/2026-10-08-trash-as-a-tombstone-on-the-row.md`
  (the measured move cost, the four studies, the ten decisions);
  `../../../research/2026-07-23-trash-prior-art-naming-and-restore.md`
  (the occupied-site refusal the field is unanimous on).

## Intent

Delete today rewrites the row's path under `/.vfs/trash/<hour>/`, every
descendant's path with it, and the path-segment postings that mirror
the column: about six row writes per file, six more on restore. The
rights algebra then undoes the move by judging every trashed row by
`origin_path`, so every visibility statement carries each piece branch
twice and the hole test as an `OR`. And the trash is a place: an agent
can `write` into it and clobber the only copy `restore` could bring
back.

After this spec a deleted row stays where it is with a timestamp on it.
Nothing moves, so permissions need one form, the postings never
change, restore is a column clear, and there is no trash to write
into. A `write` at the path brings the row back and mints a version of
the body it replaced, which is the undo the README promises.

One line: delete sets a flag, restore clears it, a write revives the
row and keeps its history, and one row per path keeps the unique
index plain on every engine.

## Decided semantics

Numbered as in ADR 074.

1. **The flag.** `vfs_entries` gains `trash_root_id` (`ULIDKey`,
   nullable) beside the existing `deleted_at`. `delete` sets both on
   the target (`trash_root_id` = its own `entry_id`) and, for a
   directory, on every live descendant (`trash_root_id` = the
   target's id), chunked by `membership_budget`. A descendant already
   tombstoned keeps its earlier values. `path`, `parent_id`, `name`,
   `everyone_level`, `owner_id`, postings and the fs edge row are
   untouched. `original_parent_id`, `original_name`, `origin_path`,
   `ix_vfs_entries_restore` and `ix_vfs_entries_origin_path` are
   dropped. The liveness index becomes
   `(deleted_at, everyone_level, path)` or `deleted_at` joins the
   existing one; the plan measures which with the statement spy.
2. **Liveness.** `liveness_filters` returns `deleted_at IS NULL` in
   every mode; the meta-subtree exclusion stays as it is. All five
   call sites inherit it. A point read, `stat`, `edit`, `move`,
   `copy`-from, `mkdir`, `mkedge` at a tombstoned path classify
   `not_found`; when the caller's rights admit the row the refusal
   carries `data["vfs.trashed"] = true` and the row's `deleted_at`.
3. **Permissions.** `RIGHTS_FIELDS` loses `origin_path`;
   `judged_path` is `path`; `visible_entries` builds one form per
   piece branch; `hole_free` is one form; `labels.py` relabels over
   `path` only; `on_trash_chain` is deleted. `restore` is gated as a
   write at the path; `destroy` stays on the developer plane.
4. **Restore.** `restore(path=…)` clears `deleted_at` and
   `trash_root_id` on the row at *path* and on every row whose
   `trash_root_id` equals its id, version-guarded, chunked. A live row
   at the path classifies `exists` (the site is occupied by the row
   itself, already live, or by a revived row of another kind, see 5).
   A tombstoned row whose parent is tombstoned and not in the same
   root classifies `not_found` for the parent, as today. The
   trash-side address form is removed; `Observation.trash_path` is
   removed and the delete observation projects `deleted_at`.
5. **Revive on write.** In the write pipeline's occupant branch, an
   occupant with `deleted_at IS NOT NULL` is a revive: the staged
   write absorbs the row's id, clears both flag columns, and mints a
   version row of the replaced body before the body update (slice B).
   A kind mismatch changes the row's kind; its tombstoned descendants
   keep their flags and `trash_root_id`, so a later `restore` of the
   directory refuses `exists` and the descendants restore one by one
   once the site is a directory again. `overwrite=False` does not
   refuse a revive: the path is not occupied by a live row.
6. **Edges.** The authored-edge cascade on delete and the
   "authored edges gone on restore" rule are removed. `graph` and
   the edge readers join `liveness_filters` on both endpoints. Reindex
   stops reclaiming edges on tombstoned endpoints.
7. **The trash view.** Enumeration scoped to `/.vfs/trash` (`ls`,
   `tree`, `glob`, `grep`, `glean`) answers tombstoned roots at their
   own paths under the caller's ordinary rights, with `deleted_at`
   projected; descendants of a tombstoned root appear under it in
   `tree`. `/.vfs/trash` itself is a synthesized directory row in the
   result, never a stored row; the hour buckets are gone. A `write`
   or `mkdir` at `/.vfs/trash/...` classifies `invalid` (the existing
   meta-root rule, extended one segment).
8. **Sweep.** `destroy /.vfs/trash` (and the retention pass)
   purges rows with `deleted_at < now − trash_days` whose
   `trash_root_id` is their own id, each with every row sharing that
   root id, chunked by id through the existing purge arm. No bucket
   name is parsed; the orphan reclaim runs as today.
9. **No other mutation reaches a tombstoned row.** The restore-only
   gate rule of spec 156 is not written; `not_found` from rule 2 is
   the answer everywhere.
10. **Scale.** Delete and restore issue a flat number of statements
    in batch size (the spy pins ≤ today's 45 and 29 at N = 1,000 and
    2,000) and touch one `vfs_entries` row per entry and zero
    `vfs_segments` rows. No dialect-specific DDL is added.

### The version mint (slice B)

A write that replaces a body — overwrite of a live file, or a revive —
inserts one `vfs_versions` row in the same transaction carrying the
replaced body (text in `content`, bytes in `data` as a snapshot per
152 §3), the replaced `version` as `version_number`, `content_hash`,
`size_bytes`, `lines`, the actor and subjects per ADR 064, and
`created_at`. Creates mint nothing. A batch mints in bulk through the
same paged insert the body takes. The read-side verb and retention are
spec 161's.

## Scope

- **Slice A — the tombstone.** Columns and indexes; `liveness_filters`;
  the rights algebra simplification; delete, restore and sweep in
  `topology.py`; the edge rules; the view; `Observation`; the router's
  `restore` docstring; the conformance suite's trash arc rewritten.
- **Slice B — the revive and the mint.** The occupant branch; the
  version insert; the bulk shape; `python -O` parity.
- Out of scope: the read-side `versions` verb and version retention
  (161); hiding tombstoned rows from the in-memory grep oracle beyond
  the shared predicate; a per-row "who deleted" column (the version
  row's actor covers the revive; delete's actor is the audit's).

## Acceptance criteria

- After `delete /d` on a directory of N files, `vfs_entries` holds the
  same N+1 paths with `deleted_at` set and `trash_root_id` = `/d`'s id;
  `vfs_segments` is unchanged; the spy counts one `UPDATE vfs_entries`
  page set and no segment statements, flat across N = 1,000 and 2,000.
- `read`, `ls`, `tree`, `glob`, `grep`, `glean`, `stat` and `graph`
  never surface a tombstoned row outside `/.vfs/trash`; one test per
  verb.
- Under a `private` posture, bob's `glob` and `tree` of `/.vfs/trash`
  show nothing of alice's deleted file; alice's show it at its own
  path with `deleted_at`. The statement for an unscoped visible read
  carries one form per piece branch (counted via the compiled SQL).
- `restore /d` clears every row sharing the root id and nothing else;
  a child deleted earlier on its own stays tombstoned.
- `write /d/f1.md` after `delete /d/f1.md` returns an `updated`
  observation with the same `entry_id`, the row is live, and
  `vfs_versions` holds one row with the old body and the caller as
  actor. `write` of a file at a tombstoned directory's path changes
  the kind; `restore /d` then refuses `exists`.
- `write /.vfs/trash/x` refuses `invalid`; `edit` at a tombstoned path
  refuses `not_found` with `data["vfs.trashed"]` true for an admitted
  caller and absent for one who could not see the row.
- `destroy /.vfs/trash` with `trash_days=0` purges every tombstoned
  root and its cascade and runs the orphan reclaim; family rows
  (content, blobs, chunks, postings, edges) go with them.
- Authored edges on a tombstoned endpoint are hidden from `graph` and
  return on restore and on revive.
- `scripts/ci.sh 3.13` green; the four engine legs green (the db_test
  skill); `cargo test -p vfs-core` untouched.
