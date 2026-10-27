# 174 — tasks

Five tasks, landing in order. Each lands green through
`scripts/ci.sh` (lint, format, types, 100% coverage). Tasks 2, 3 and
4 add `StorageContract` rows, so they run on every engine leg in CI;
task 4 also runs the four real-engine legs locally (the `db_test`
skill) and a `scale_review` before it lands, because it adds a
locking read and a new isolation path.

## 1. `unchanged` (spec §3) — no API change

- `_fetch_committed` (`writes.py`) selects `content_hash`.
- `WritePlan.settle()` and `_same_material` (`staging.py`); `_mark`
  rewrites a path's pending statuses. `_finish` calls `settle()`
  first. `StagedEntry.expected_version` lands here as an always-`None`
  field, so task 3 only fills it.
- `edit` inherits the rule through `_finish`.
- Tests: criteria 3 to 9. In `test_writes.py`, the identical-rewrite
  count (1 non-control statement, 0 mutations) and the 10,000-row
  identical rewrite (0 entry rows, 0 content rows written). In
  `StorageContract`: `test_an_identical_write_is_unchanged_and_keeps_its_version`,
  `test_a_mixed_batch_writes_only_what_changed`,
  `test_a_batch_that_writes_a_path_back_to_its_body_is_unchanged`,
  `test_a_new_mime_or_source_on_the_same_body_is_an_update`,
  `test_an_edit_that_changes_nothing_is_unchanged`,
  `test_a_revive_with_the_old_body_is_updated`.
- Existing tests that rewrite a body identically and expect
  `updated` or a version bump move to a different body, or assert
  `unchanged`.
- Docs: `docs/explanation/ownership-and-attribution.md` line 49
  ("the version counter still moves") states the new rule.

## 2. `if_absent=` replaces `overwrite=` on `write` (spec §1, §5)

- Router, `Session.write`, `PARAMS["write"]` and its rules, the seam
  (`SupportsMutation.write`), `DatabaseStorage.write`,
  `write_rows(if_absent=)` mapping to the internal `overwrite`.
  `tests/support/base_doubles.py` follows the seam.
- `ops.ADDITIVE_WRITE` and its invariant test; `DatabaseStorage.write`
  passes it to the gate under `if_absent`.
- `put_file` judges `if_absent` before the kind check; `put_dir`
  gains `exclusive`. `occupied(path, row)` (in `staging.py`) puts `version` and
  `content_hash` in `exists`; the arbitration occupant probes
  (`_classify_arbitration_loss`, `_resolve_rows`) select
  `content_hash`.
- `results/kinds.py`: the `exists` data record.
- Every `overwrite=` call site in `tests/` and the `exceptions.py`
  docstring move to `if_absent=`.
- Tests: criteria 16, 17, 18, and 25's `overwrite` half. Contract rows
  `test_if_absent_creates_an_absent_file`,
  `test_if_absent_over_a_live_file_is_exists_with_its_version_and_hash`,
  `test_if_absent_over_a_directory_is_exists`,
  `test_if_absent_revives_a_tombstone`,
  `test_twenty_racing_if_absent_creates_admit_exactly_one`.

## 3. `if_version=` and `if_versions=` (spec §1.3, §1.4, §4)

- `params.py`: the `"versions"` kind and its item check; the shape and
  value rules of §1.3.
- `base.py`: the single form becomes a one-key mapping; key resolution
  and rebasing in `_route_entry_batch`; the batch refusals of §1.3.
  `Session.write` mirrors.
- The seam and `DatabaseStorage.write` carry `if_versions`.
- `staging.py`: `put_file` sets `expected_version`; the
  missing-row and tombstone refusals (§4.2); `settle` refuses a stale
  update (`stale_version`, in `staging.py`, `retryable=False`).
- `writes.py`: `_classify_guard_misses` selects `version` and
  `content_hash`; a miss whose current hash equals the staged one
  raises `StaleSnapshot`; every other miss is a `conflict` carrying
  `version`, with `retryable` `False` for a row with an expected
  version.
- `results/kinds.py`: the `conflict` data record and the `retryable`
  rule, stated once.
- Tests: criteria 2 and 10 to 15. The race (criterion 12) lives in
  `test_races.py` using the `write:before-apply` seam, on the SQLite
  file leg and in the contract for the engine legs. The 10,000-row
  batch (criterion 14) narrows `in_list_budget` to 1,000 the way
  `test_graph.py` does. Contract rows
  `test_a_stale_if_version_is_conflict_and_writes_nothing`,
  `test_a_passing_if_version_updates`,
  `test_a_replay_of_ones_own_if_version_write_is_unchanged`,
  `test_if_version_on_a_missing_or_deleted_row_is_not_found`,
  `test_one_stale_key_refuses_the_whole_batch`.

## 4. `append=True` (spec §6, §7)

- `models/version.py` takes `MEASURE_OFFLOAD_BYTES` from `base.py`.
- `storage/editing.py`: `appended(...)`, with unit tests for the four
  source cases of criterion 19.
- `writes.py`: `_lock_targets`; `_fetch_committed(bodies=True)`; the
  compose loop through `WritePlan.body_of` and the measure hop
  (`call_offloaded` at or above the threshold); arbitration loss and
  guard miss raise `StaleSnapshot` for a row with `append = True`.
- `staging.py`: `StagedEntry.append`, `base_data`, `body_of`.
- `versions.py`: the mint reuses `base_data`.
- `backend.py`: `_execute_append`; `write(append=True)` uses it and
  `ADDITIVE_WRITE`. `dialects.py`: the `topology_execution_options`
  and `topology_isolation` docstrings name the append.
- Router, session, params: `append` and its two ingress rules.
- Tests: criteria 1 and 19 to 24. The 20-task probe is a contract row
  (`test_twenty_concurrent_appends_keep_twenty_lines`, from an
  existing file and from an absent path); the statement counts, the
  10,000-row batch and the offload spy are in `test_writes.py`.
  Contract rows also `test_append_extends_a_bytes_row`,
  `test_append_keeps_the_rows_source_when_the_body_allows`,
  `test_an_add_holder_appends_to_another_row_but_cannot_overwrite_it`.
- Before landing: the four real-engine legs (`db_test`), and
  `scale_review` on the lock read and the body join.

## 5. Docs and close-out

- `docs/reference/api.md`: the `write` arguments, the refusal table
  of spec §8, and a short "read, change, write back" example with
  `if_version`.
- `docs/reference/glossary.md` and the `Rung` docstring in `ops.py`:
  `add` appends to any row it may read.
- Hand back to the session lead for the ADR amendments, the
  open-questions archive entry and the rebase notes (spec 174's last
  three sections), which this spec does not edit itself.
