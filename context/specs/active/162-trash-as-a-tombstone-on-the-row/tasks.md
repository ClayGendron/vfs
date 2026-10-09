# 162 — Tasks

Each task leaves `scripts/ci.sh 3.13` green. Slice A tasks 1–9 land
together or in the order given; slice B follows.

## Slice A

1. [ ] `models/rows.py`: add `trash_root_id` + index; drop the three
   origin columns and their indexes; measure and pick the liveness
   index; update `tests/models/test_rows.py`.
2. [ ] `models/entry.py`: remove `Observation.trash_path` and its
   rebase arm; add `deleted_at` to the delete projection
   (`results/projection.py`).
3. [ ] `descent.py`: the liveness term; the `vfs.trashed` hint in the
   point-read ladder; tests in `test_reads.py`.
4. [ ] `ranges.py` / `rights.py` / `labels.py` / `paths.py`: one form
   per branch; remove `origin_path` everywhere; delete
   `on_trash_chain`; compiled-SQL arm-count test; `test_ranges.py`,
   `test_rights.py`, `test_labels.py` updated.
5. [ ] `topology.py` delete: the flag cascade; remove the rewrite
   helpers and segment moves; remove the authored-edge cascade.
6. [ ] `topology.py` restore: clear by root id; remove the lookup
   shapes; router docstring.
7. [ ] `topology.py` sweep: expired roots by `WHERE`; purge by root id
   set; remove bucket parsing and squatter warnings.
8. [ ] `reads.py` / `scope.py` / `base.py`: the trash view; the
   synthesized `trash` row; the write gate's `/.vfs/trash` rule
   (`tests/base/test_gates.py` L247–254 flips).
9. [ ] `edges.py` / `indexing.py` / `graph`: liveness on endpoints;
   remove the reclaim.
10. [ ] Tests: rewrite `test_trash.py`; conformance trash arc;
    the statement-and-row counting test at N = 1,000 and 2,000; the
    private-posture listing test; one never-surfaces test per verb.
11. [ ] Run the four engine legs (db_test skill).

## Slice B

12. [ ] `writes.py`: the revive in the occupant branch; kind change;
    `overwrite=False` liveness check.
13. [ ] `versions.py`: the bulk mint for live overwrite and revive;
    actor and subjects from the authority.
14. [ ] Tests: identity kept; version row contents; page-count parity
    with body inserts; kind change then `restore` refuses `exists`;
    `python -O` parity.
15. [ ] Spec 161: update its status to "mint landed by 162 slice B;
    read-side verb and retention remain".
16. [ ] On landing: move 162 to `archive/`; status lines on archived
    081, 082, 083 note the supersession; README verb table regains the
    "versioned" sentence (spec 153 note).
