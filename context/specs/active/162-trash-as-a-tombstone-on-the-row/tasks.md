# 162 — Tasks

Each task leaves `scripts/ci.sh 3.13` green. Slice A tasks 1–10 land
together or in the order given; slice B follows. Task 0 gates both.

0. [ ] Clay confirms the two ADR 074 amendments in spec rules 4 and 5
   (only a root restores; same-kind revive only; `overwrite=False`
   admits a revive) and the ADR's status line records them. **Built
   on these as working answers (2026-10-11); still unconfirmed.**

## Slice A

1. [x] `models/rows.py`: add `trash_root_id` + index; drop the three
   origin columns and their indexes; `ENTRY_ROW_ONLY_COLUMNS`;
   `SCHEMA_FORMAT_VERSION`; measure and pick the liveness index;
   update `tests/models/test_rows.py`.
2. [x] `models/entry.py`: remove `Observation.trash_path` and its
   rebase arms; add `deleted_at` to the delete projection
   (`results/projection.py`).
3. [x] `descent.py` / `writes.py`: the liveness term; `deleted_at` on
   the point fetch, the ancestor query and `_fetch_committed`; the
   `vfs.trashed` hint; the parent gate; tests in `test_reads.py` and
   `test_writes.py`.
4. [x] `ranges.py` / `rights.py` / `labels.py` / `paths.py`: one form
   per branch; remove `origin_path` everywhere; delete
   `on_trash_chain`; `check_mutable_path` docstring; compiled-SQL
   arm-count test; `test_ranges.py`, `test_rights.py`,
   `test_labels.py` updated.
5. [x] `topology.py` delete: the flag cascade; remove the rewrite
   helpers and segment moves; remove the authored-edge cascade.
6. [x] `topology.py` restore + `backend.py` L740–760: clear by root
   id; root-only; remove the lookup shapes; router docstring.
7. [x] `topology.py` sweep: expired roots by `WHERE`; purge by root id
   set; remove bucket parsing and squatter warnings.
8. [x] `reads.py` / `scope.py` / `base.py`: the head strip and the
   flipped term; `ls` of the head and of a tombstoned directory; the
   synthesized `trash` row; the write gate's `/.vfs/trash` rule
   (`tests/base/test_gates.py` L247–254 flips).
9. [x] `edges.py` / `links.py` / `indexing.py` / `backend.py`:
   liveness on endpoints; remove the reclaim; docstrings.
10. [x] Tests: rewrite `test_trash.py`; conformance trash arc; the
    statement-and-row counting test at N = 1,000 and 2,000; the
    private-posture listing test; one never-surfaces test per verb;
    the EXPLAIN pin; STATUS.md.
11. [ ] Run the four engine legs (db_test skill). **Not run 2026-10-11** (needs Docker).

## Slice B

12. [x] `staging.py` / `writes.py`: the revive mark on a same-kind
    tombstoned row; `wrong_kind` on mismatch; `overwrite=False`
    liveness check; `_CLOBBER_COLUMNS`.
13. [x] `versions.py`: the pre-image select; the bulk mint with
    `is_snapshot`, attribution and `read_revision`; the subject rows.
14. [x] Tests: identity kept; version row contents; bounded statement
    count against `rows_per_statement`; kind mismatch refuses;
    directory revive mints nothing; `python -O` parity.
15. [ ] Spec 161: status to "mint landed by 162 slice B; read-side
    verb, retention and the ADR remain".
16. [ ] On landing: move 162 to `archive/`; status lines on archived
    081, 082, 083 note the supersession; spec 156's rule 2 stub and
    spec 150 §8's note point here. The README's versioning sentences
    return with 161's read-side verb, not here (spec 153).
