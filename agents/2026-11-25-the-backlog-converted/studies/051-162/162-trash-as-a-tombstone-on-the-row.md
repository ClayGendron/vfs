# Study: Trash as a tombstone on the row: delete flags, restore clears, a write revives

## Verdict

Landed. Both slices are in the tree: the tombstone columns and indexes, the one-form rights algebra, delete, restore and sweep as column updates in `trash.py`, the `/.vfs/trash` view, the revive on write and the version mint in `versions.py`. The open tasks are housekeeping only (the archive move, status lines on archived 081, 082, 083 and active 161, spec 156's and 150's pointers), which roadmap story R7 criterion 1 already names; the one unrun check, the three non-Postgres engine legs, is now covered by the `Dialect tests` workflow on every push and pull request that touches storage. The spec is archived with a landing note; it is not converted.

The design the spec landed is itself under review: the 2026-11-15 deletes memo finds tombstones right for undo and wrong for freeing a path, and the not-yet-written deletes spec will change the unique keys, the revive and the name of `sweep`. That is new work for the deletes spec, not a reason to keep 162 open.

## Against the tree

The tree was read at `09dad59` (the working checkout; `0ed462f` is its ancestor, and the commits between touch only `agents/`) (EXECUTED, `git log`).

Slice A, the tombstone:

- `vfs_entries` carries `deleted_at` and `trash_root_id` with the comment "The tombstone: a deleted row stays at its path" (READ, `src/vfs/models/rows.py:482-485`); `ix_vfs_entries_deleted_at` and `ix_vfs_entries_trash_root` exist, as the landing note says, rather than a prepended `ix_vfs_entries_everyone_path` (READ, `src/vfs/models/rows.py:496-500`). `trash_root_id` is in `ENTRY_ROW_ONLY_COLUMNS` (READ, `src/vfs/models/rows.py:87`).
- `origin_path`, `original_parent_id`, `original_name`, `on_trash_chain` and `Observation.trash_path` appear nowhere in `src/vfs` source (EXECUTED, grep; only stale `.pyc` caches matched).
- The root predicate `trash_root_id == entry_id` lives in `descent.py` (READ, `src/vfs/storage/backends/database/descent.py:216-217`).
- `trash.py` owns delete, restore and sweep, as the landing note's three-file split says: the delete sets `deleted_at` and `trash_root_id` in one bound update (READ, `src/vfs/storage/backends/database/trash.py:495`), restore clears both and bumps the version (READ, `trash.py:526`), a non-root refuses with `vfs.trash_root` (READ, `trash.py:252-253`), and sweep chunks the expired roots by `trash_root_id` membership (READ, `trash.py:388-399`). `topology.py` keeps move and copy; `serialized.py` is the shared kit (EXECUTED, `ls src/vfs/storage/backends/database/`).
- The hint keys are `vfs.trashed` and `vfs.trash_root` (READ, `src/vfs/results/kinds.py:21-23`).
- The view's address is `TRASH_ROOT = "/.vfs/trash"` and `is_trash_path` names it as "nothing is stored there" (READ, `src/vfs/paths.py:47`, `:766-773`).
- `tests/storage/database/test_trash.py` exists and holds `TestStaleSnapshotGuards`, the landing review's guard pin (READ, `tests/storage/database/test_trash.py:616`).

Slice B, the revive and the mint:

- `staging.py` marks a same-kind tombstoned target `revive = True` and documents that `parents=True` never revives a deleted directory (READ, `src/vfs/storage/backends/database/staging.py:82`, `:250`, `:287`, `:325`).
- `writes.py` carries `trash_root_id` among the clobber columns and nulls it on the revive (READ, `src/vfs/storage/backends/database/writes.py:135`, `:1226`).
- `versions.py` is "the write path's one history writer": it mints on overwrite, revive and arbitration clobber, skips creates, bodiless rows and identical bodies, reads the pre-image under the entry row lock and pages the insert by budget (READ, `src/vfs/storage/backends/database/versions.py:1-34`). `vfs_versions` with `is_snapshot` and `vfs_version_subjects` exist (READ, `src/vfs/models/rows.py:543-569`).

Engine legs: task 11 records Postgres green on 2026-10-12 and MariaDB, SQL Server and Oracle not run (READ, `tasks.md:19`). `.github/workflows/test-dialects.yml` now runs all four engines on every push to `main` and every pull request touching `src/vfs/storage/**`, `src/vfs/models/**` or `tests/**` (READ, `.github/workflows/test-dialects.yml:1-49`). Every storage landing since 2026-10-12 has passed through it, so the tombstone paths have run on all four engines (INFERRED; no run log was read here).

Later work built on the tombstone rather than replacing it: archived specs from 2026-10-31 onward name tombstones and trashed rows as given, for example the index-pending index's `deleted_at` column and the 2026-11-14 commit-point authorization spec (EXECUTED, grep of `context/specifications/archive/2026-1*`; READ, `src/vfs/models/rows.py:492`).

The problem statement (delete rewrote paths under `/.vfs/trash/<hour>/`, rights judged twice by `origin_path`) is no longer true at HEAD: that is the change the spec made (INFERRED from the reads above).

## Where the roadmap places it

- Roadmap §13's count line lists 162 among "4 built but not archived (165, 162, 152 A/B, 173)" (READ, `context/standards/roadmap.md:106`, repeated at `:897`).
- Story R7, the context-pipeline true-up, gate b, criterion 1: "Specs 165, 162, 152 …, 173 move to `specifications/archive/` with landing notes; their stale 'uncommitted' lines are corrected first" (READ, `context/standards/roadmap.md:962-965`). Criterion 2 drops spec 161 because "its write half landed with the tombstone mint" (READ, `roadmap.md:966`).
- The third promise records "Trash and restore are built" (READ, `roadmap.md:36`); the release notes criterion lists "trash-as-tombstone" among the shipped features (READ, `roadmap.md:927`).
- The successor is placed by no story yet: the kernel rulings spec says the deletes spec's landing adds its own roadmap story before R5 draws the freeze list (READ, `context/specifications/active/2026-11-15-the-kernels-public-names-and-argument-families-are-ruled.md:144`).

## Units proposed

None. The spec is landed; its remaining work is R7 criterion 1's archive move with a landing note, and that note is a pipeline act, not a buildable spec (INFERRED).

The archive note should say: both slices built and committed 2026-10-12 (`7d0bc3c` and the review's fixes); the "uncommitted, awaiting review" status line is stale; the three non-Postgres legs are run by `test-dialects.yml`; tasks 15 and 16 are discharged by R7 (161 dropped; 081, 082, 083 already archived as superseded); the deletes spec revisits the design (READ, `spec.md:3`, `tasks.md:19`, `:26-27`).

## Open choices, each verified

1. Only a root restores; a child of a tombstoned root is `not_found` naming the root (rule 4, the ADR 074 amendment). Already-ruled: confirmed 2026-10-13 and built (READ, `tasks.md:5`; `trash.py:252-253`).
2. Revive keeps the row's kind; a kind mismatch refuses `wrong_kind`; `overwrite=False` admits a revive (rule 5). Already-ruled: decided 2026-10-13 (READ, `spec.md:27`, `tasks.md:5`). The `overwrite=` half is restated by the kernel rulings: `overwrite=` is removed for `if_absent=` (K2), and `write(if_absent=True)` on a tombstone revives (READ, `roadmap.md:147`; kernel rulings spec `:144`). The deletes memo finds this revive the second most serious failure (a new file at a deleted path becomes the old file and keeps the first owner) (READ, `context/research/2026-11-15-deletes-tombstones-and-a-move-that-keeps-its-identity.md:19-25`); revisiting it is the deletes spec's choice, not 162's.
3. The liveness index: prepend `deleted_at` to `ix_vfs_entries_everyone_path` or add a separate index (rule 1, "the plan's measurement"). Already-ruled by the landing: two single-column indexes, because a leading `IS NULL` is not an access predicate on Oracle (READ, `spec.md:62`; `rows.py:496-500`).
4. A body replaced by an identical one mints nothing. Already-ruled: decided 2026-10-12 at the landing review and built (READ, `spec.md:73`; `versions.py:12-15`).
5. Same-kind revive versus the ADR's kind change, recorded as "awaits … amendment of ADR 074 item 5" (READ, `plan.md:27`). Already-ruled: the 2026-10-13 confirmation closed it; the plan line is stale (READ, `tasks.md:5`).
6. Task 11, the MariaDB, SQL Server and Oracle legs. Already-ruled in effect: the CI workflow runs them on every storage change (READ, `.github/workflows/test-dialects.yml:9-49`).

The spec holds no `[NEEDS CLARIFICATION]` marker (EXECUTED, read of the three files).

## What is stale

- Status line "in the working tree, uncommitted, awaiting … review" and "MariaDB, SQL Server and Oracle have not run": the work is committed and the legs run in CI (READ, `spec.md:3`; `test-dialects.yml`).
- `topology.py` as the home of delete, restore and sweep (spec rules 4, 8; plan A4–A6; tasks 5–7): they live in `trash.py`, with `serialized.py` as the shared kit (EXECUTED, `ls`; READ, `spec.md:77`).
- "`destroy /.vfs/trash`" (spec rule 8, rule 3): at HEAD the verb is `sweep` with default path `/.vfs/trash` (READ, `src/vfs/base.py:1119-1136`, `src/vfs/session.py:199`); D56 decided 2026-11-15 that it becomes `destroy`, and D57 decided 2026-11-15 who may call it; both are the deletes spec's to build (READ, `roadmap.md:1128-1129`).
- `overwrite=False` (rule 5): ruled to be replaced by `if_absent=` under K2; the tree still has `overwrite: bool = True` (READ, `src/vfs/base.py:967`; `roadmap.md:147`).
- `glean` among the scoped verbs (rules 7, acceptance): renamed `search` (and `graph` → `traverse`) by the archived 2026-11-09 verb-naming spec (READ, `context/specifications/archive/2026-11-09-the-verbs-take-the-names-agents-know.md:3`).
- ADR 074, 064, 017, 072, 073, 077 as dependencies: the decision records were retired 2026-10-30 (commit `3667fec2`) (READ, `roadmap.md:106`).
- Line citations (`staging.py L265–267`, `writes.py L259–285`, `L600–709`, `L916–918`, `backend.py L740–760`, `entry.py L464`, `descent.py L167–174`): written against `0760fe9`; the code they point at has moved (for example `_CLOBBER_COLUMNS`' tombstone entries now near `writes.py:135`) (READ; INFERRED for the rest).
- Task 15 (spec 161's status) and the reference to 161 owning the read-side verb: the read half is roadmap story K8 and 161 is to be dropped (READ, `roadmap.md:36`, `:966`).
- The spy counts "≤ today's 45 and 29" (rule 10): the landing pinned ≤ 10 statements flat in N (READ, `spec.md:76`).

## Notes for the conversion

- No conversion. Archive the folder under R7 criterion 1 with the landing note above; do not edit its body beyond correcting the status line, which R7 asks for first.
- The successor is the deletes spec, which no unit of this study proposes: it stands on the 2026-11-15 deletes memo (READ, `context/research/2026-11-15-deletes-tombstones-and-a-move-that-keeps-its-identity.md:11-29`, `:75-86`) and carries D55 (a replacing move keeps the moved file's identity; the replaced file stays undoable), D56 (`destroy`) and D57 (who may destroy), all decided 2026-11-15 (READ, `roadmap.md:1127-1129`). Its findings that bear on 162's landed rules: a deleted row holds its path under both unique keys, so a deleted folder's name is dead; a write at a deleted file's path revives the old row with its old owner; `sweep` at a live path destroys live data at `delete`'s rung; a listing visits every tombstoned child (EXECUTED in the memo on SQLite). The memo's lean is a generation number in the unique keys (READ, memo `:13`).
- A writer converting a neighbouring spec (161, 102, 176, 180, 181) should treat the tombstone, `trash_root_id`, the root-only restore and the mint as the tree's current fact, and anything about freeing a path, `replace=`, or `destroy` as waiting on the deletes spec (INFERRED).
- The roadmap's ladder row says `/.vfs` serves only the trash view (READ, `roadmap.md:101`); stories T2–T4 add heads beside `trash`, which 162 leaves untouched.
