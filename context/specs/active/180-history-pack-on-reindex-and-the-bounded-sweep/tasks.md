# 180 — tasks

Nine tasks, landing in order. Each lands green through
`scripts/ci.sh` (lint, format, types, the suite at 100% coverage).
Tasks 3, 5 and 6 also run the four real-engine legs (`db_test`)
before they land, and task 9 runs a scale review. Tasks 1 to 5 need
nothing from spec 176; tasks 6 to 8 wait for 176's `Result` key field
and its `after=` / `limit=` grammar.

## Pack (spec §1–§4, §9)

1. **Schema and the mint.** Add `vfs_versions.packed` and
   `vfs_versions.stored_bytes`, the index `ix_vfs_versions_packed
   (packed, entry_id)`, and bump `SCHEMA_FORMAT_VERSION` to the next value (176 and 177 land first). Add
   both columns to `VERSION_ROW_ONLY_COLUMNS`. The mint's
   `_version_row` sets `packed=False` and `stored_bytes=size_bytes`.
   Rewrite the `vfs_versions` comment to name the pack phase. Retire
   `create_version` and `VersionRecord`; `Version.create` builds the
   snapshot form only. Tests: the drift tests, the mint's columns, and
   criterion 13's unchanged statement count.
2. **The planner.** Add `PACK_HOT_ROWS`, `PACK_MAX_BODY_BYTES`,
   `PackRow`, `PackDecision`, `PackPlan` and `plan_pack` to
   `models/versioning.py`, following the chain law's seven rows
   (spec §2). Unit tests cover every row of the table, the cadence
   (one snapshot and at most nine diffs), rot (the row and its
   successor stay whole), bytes (never diffed, never diffed across),
   the size gate, "never larger than the body", and incremental
   planning equal to whole planning (criterion 5 at the model level).
3. **The phase.** Add `storage/backends/database/pack.py` with the
   work-list select, the metadata read, the slice cut, the body read
   and the landing (spec §3.3–§3.4). Move `_flip_flags`'s set-based
   triad to `dialects.py`, generalized to a table and its key columns,
   and point the index flips at it. Add `_pack_step` as the last step
   of `_reindex_phases`, the `pack` extra, the rot warning, and the
   seams `pack:before-land` and `pack:after-anchor`. Tests: criteria
   1–12 (the 10,000-file corpus marked `slow`), on SQLite and the four
   engine legs.

## Gauge (spec §6)

4. **`garbage()`.** Add `SupportsGarbage` to `storage/protocol.py`
   and `DatabaseStorage.garbage()`: two statements in one read
   transaction, the tombstone aggregate spelled as a `deleted_at`
   range so it seeks the index. Tests: criteria 22–23, with an
   access-path pin that the first statement seeks
   `ix_vfs_entries_deleted_at` on SQLite.

## Sweep (spec §5)

5. **Slices, without the key.** Split `sweep_rows`'s retention arm
   into a roots slice and an orphan slice, each its own transaction
   under `serialize`, and loop them in `DatabaseStorage.sweep` until
   done. The roots select takes `ORDER BY deleted_at LIMIT :slice`.
   The orphan pass walks `vfs_content`, `vfs_blobs` and `vfs_versions`
   (with `vfs_version_subjects`) in `entry_id` windows, three
   statements per family per slice, and replaces
   `_reclaim_orphan_content`'s whole-table anti-join. The purge arm is
   unchanged. Tests: criteria 15, 17 (without the key), 18 and 19;
   `test_a_retention_sweep_issues_a_flat_number_of_statements_in_roots`
   stays green. Engine legs.
6. **`limit=` and `after=`.** After spec 176 lands: `SweepMark`, the
   key's payload inside 176's envelope, `limit` and `after` on the
   router, `PARAMS`, the protocol and the backend; `invalid` for a bad
   key, a foreign mount's key, and either argument at a non-trash
   address. Tests: criteria 14, 16, 20 and 21. Engine legs.

## History read (spec §7, §8)

7. **`versions(path)`.** Add `Observation.actor` and its mirror
   entry. Add `"versions"` to `Op`, `READ_OPS`, `VERB_RUNGS`
   (`Needs("read")`), `PARAMS` and the default projection. Add
   `SupportsHistory` and its `_FAMILY_OPS` row, the router method, and
   `DatabaseStorage.versions` through `_viewed`, with
   `HISTORY_PAGE_ROWS` and the key (entry id plus last label). Tests:
   criteria 24–26 and 28, plus the op-class drift tests.
8. **`read(path, version=N)`.** Add `version` to `read`'s params
   (`OnlyWith("version", "path")`), the protocol and the backend: the
   live body at the current version, the chain fetch otherwise,
   `Version.reconstruct` behind `call_offloaded` above the offload
   threshold, one re-read when a chain does not start at a snapshot,
   and spec 175's integrity kind on a mismatch. The router refuses
   `unsupported` when the mount lacks `"versions"`. Tests: criteria 2,
   8 (the read half), 27, 29 and 30. Add the history family to
   `tests/support/storage_contract.py`.

## Close-out

9. **Docs, review, legs.** Add `versions` and `read(version=)` to the
   README verb table and the reference docs; document `garbage()` and
   the sweep loop for deployment jobs beside `reindex()`. Run the
   scale review on the pack, sweep and history statements at a
   10,000-file batch and on Oracle's 1,000-key budget, and the four
   engine legs. Hand the ADR amendments and the rebase notes to the
   session lead. Fill in the landing notes.
