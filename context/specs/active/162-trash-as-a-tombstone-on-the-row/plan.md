# 162 — Plan

Two slices, each landing green. Slice A is a removal as much as a
build: the move, the origin columns and the trashed rights forms come
out; the flag, the view and the cascade go in. Slice B adds the revive
and the mint on the write path.

## Slice A — the tombstone

1. **Row model** (`models/rows.py`). Add `trash_root_id` (`ULIDKey`,
   nullable, indexed as `ix_vfs_entries_trash_root`). Remove
   `original_parent_id`, `original_name`, `origin_path` and their two
   indexes. Decide the liveness index by measurement: run the
   statement spy on the unscoped visible read with `deleted_at`
   prepended to `ix_vfs_entries_everyone_path` versus a separate
   single-column index, and keep the one whose plan seeks on every
   engine leg (the `EXPLAIN` harness in `tests/storage/database/
   test_ranges.py` is the model). `Entry.deleted_at` already exists;
   `Observation.trash_path` is removed and `deleted_at` joins the
   delete projection.
2. **Liveness** (`descent.py`). `liveness_filters` returns
   `[entry.c.deleted_at.is_(None), *meta_terms]`; `include_meta`
   keeps its meaning for the meta subtree only. Five call sites need
   no change. Add the `vfs.trashed` hint: `classify_descent` (the
   point-read ladder) looks the row up without the liveness term when
   the path misses with it, and if a tombstoned row exists and
   `visible_entries` admits it, attaches `data`.
3. **Rights algebra** (`ranges.py`, `rights.py`, `labels.py`,
   `paths.py`). Delete the `columns` loop in `visible_entries` and
   build each branch once on `path`; collapse `hole_free` to its live
   form; `judged_path` returns `path`; drop `origin_path` from
   `RIGHTS_FIELDS` and `judged_columns`; `labels.py` relabels over
   `path` only; delete `on_trash_chain` and `is_trash_path`'s
   chain-holder uses that only the move needed (keep `TRASH_ROOT`
   for the view's address). Pin with a compiled-SQL test that counts
   `UNION ALL` arms for a fixed `Ranges`.
4. **Delete** (`topology.py`). `delete_rows` keeps its gate, its
   lock, its version guard and its chain-holder refusal shape, and
   replaces `_reparent_to_trash`, `_descendant_rewrites`,
   `_apply_rewrites`, `_rewrite_descendants`, `_trash_name`,
   `_subsumed_trash_path`, `_bucket_hour` and the segment moves with
   one chunked `UPDATE … SET deleted_at = :now, trash_root_id = :root
   WHERE deleted_at IS NULL AND (entry_id = :root OR path LIKE
   :subtree ESCAPE …)`; the descendant set is the same `descendant_
   filter` the rewrite used. Remove the authored-edge cascade. The
   observation reports `status="deleted"` and `deleted_at`.
5. **Restore** (`topology.py`). `restore_rows` resolves *path* to a
   row with the liveness term off; a live row is `exists`; a
   tombstoned row whose parent is tombstoned under a different root
   is `not_found` on the parent; otherwise one chunked `UPDATE … SET
   deleted_at = NULL, trash_root_id = NULL WHERE trash_root_id =
   :root`, guarded on the root's version. Delete `_lookup_restore`,
   `_restore_site`, `_point_restore_row`, `_newest_candidate` and the
   `RestoreLookup` shapes. The router's `restore` docstring loses the
   trash-side address sentence.
6. **Sweep** (`topology.py`). `sweep_rows` at the trash root selects
   expired roots (`trash_root_id = entry_id AND deleted_at <
   :cutoff`), chunked, and feeds each root's id set (`WHERE
   trash_root_id = :root`) to `_purge_subtree`; the squatter and
   bucket warnings go; the orphan reclaim stays. Elsewhere `sweep`
   is the wholesale purge it is today.
7. **The view** (`reads.py`, `scope.py`). When `meta_scoped(pattern)`
   or the scope path names `/.vfs/trash`, the enumeration's liveness
   term flips to `deleted_at IS NOT NULL` and, for `ls`, `trash_root_id
   = entry_id`; `tree` descends by the usual parent walk with the
   flipped term. `ls /.vfs` answers the synthesized `trash` row. The
   write gate's meta-root rule extends to `/.vfs/trash` as a target.
8. **Edges** (`edges.py`, `indexing.py`). Remove the delete cascade
   and the reindex reclaim of edges on tombstoned endpoints; the edge
   readers and `graph` add the liveness term on both endpoint joins.
9. **Tests.** `tests/storage/database/test_trash.py` (45 tests, most
   about buckets, names and rewrites) is rewritten around the ten
   decisions; `tests/storage/test_conformance.py`'s trash arc follows;
   `test_rights.py` and `test_ranges.py` lose their origin cases and
   gain the private-posture trash listing; the spy from the memo
   becomes a counting test (statements and rows, never time).

## Slice B — the revive and the mint

1. **Occupant branch** (`writes.py` L578–597). The occupant query
   adds `deleted_at`; an occupant with it set is a revive:
   `staged.absorb(occupant.entry_id)` plus a `revive` mark the
   material update turns into `deleted_at = NULL, trash_root_id =
   NULL`, kind set from the staged entry. The `overwrite=False`
   refusal checks liveness first.
2. **The mint** (new `versions.py` beside `writes.py`). For every
   staged replace (live overwrite or revive), select the replaced
   body and metadata under the row lock the write already holds, and
   insert the version rows in bulk (the driver's executemany, paged by
   bytes inside the bind-count page as 152 does). Actor and subjects
   come from the authority the write carries (ADR 064).
3. **Tests.** Revive keeps `entry_id`; version row holds the old body
   and actor; a 2,000-file overwrite batch issues version inserts in
   the same number of pages as body inserts; kind change on revive
   and the following `restore` refusal; `python -O` parity.

## Trade-offs recorded

- Flipping the liveness term for the view (A7) is one predicate, not a
  second scope concept; the alternative, a `trashed=` parameter on the
  verbs, was rejected to keep `/.vfs/trash` the address `destroy` and
  agents already use.
- The cascade `UPDATE` touches every descendant row once; a
  "inherit from ancestor" design was rejected because every read would
  need an ancestor check.
- Dropping the origin columns is a schema change on a greenfield
  tree; no migration is written.
