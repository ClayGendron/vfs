# 179 — tasks

Five slices: A (the seam's vocabulary), B (derived operations and the
feature gate), C (counters and the fold), D (the battery split), E
(the three families). They land in the order below, not in slice
order: the split first, so every later test has its home; the meters
and the golden tables before the fold, so the fold lands as a reviewed
diff; the derived operations last, because their feature rows fill in
as specs 174, 176, 177, 178 and 180 land.

Each task lands green through `scripts/ci.sh` (lint, format, types,
tests at 100% coverage, the docs fences, the wheel budget). Tasks 4, 5,
8, 9, 10, 11 and 13 also run the four engine legs (the db_test skill)
before landing. No task touches `crates/`.

## Slice D — the battery split (spec §6)

1. **Split the conformance battery into `tests/support/contract/`.**
   Save `pytest --collect-only -q tests/storage/test_conformance.py`.
   Move every test of `storage_contract.py` and `grants_contract.py`
   into the twelve files of §6.1, by the line ranges there, with no
   assertion changed. Compose `StorageContract` and `GrantsContract` in
   `contract/__init__.py`. Give the 27 glob tests their own banner.
   Change only the import line in `test_conformance.py`. Delete the two
   old files. The saved list equals the new one, line for line
   (criterion 15).

## Slice A — the seam's vocabulary (spec §1, §2, §3)

2. **The groups and the families.** Add `OpGroup`, `OP_GROUPS` and
   `GROUP_OF` to `ops.py` in spec 181 §2.1's exact shape, with its
   drift tests. Rewrite the `Supports*` protocols by kernel group
   (§1.2), `_FAMILY_OPS` and `storage_ops`, and the exports in
   `storage/__init__.py`. Delete `SupportsRead`, `SupportsMutation`,
   `SupportsGrants`, and `SupportsRun` with `run` if spec 167 slice A
   has not. Point `_call_storage`'s `isinstance` checks at the new
   families. Update `tests/storage/test_protocol.py` (criteria 1–3).
3. **The declarations.** Add `Feature`, `FEATURES`,
   `FEATURE_ARGUMENTS` (empty), `FEATURE_FALLBACK` and `DERIVED_FROM`
   to `ops.py`; `SupportsFeatures`, the `atomic_unit` trait,
   `"none"` durability, `Atomicity`, `METHOD_ATOMICITY` and
   `ENGINE_ERROR_KEY` to `protocol.py`; the three docstring sections
   (§3.2) and the `base.py` and `write` docstring sentences.
   `DatabaseStorage.features()` and the `atomic_unit` trait.
   `MountMeta.declared_features`, its refresh, and
   `MountInfo.features`. The feature/trait consistency rows go in
   `contract/maintenance.py` (criteria 4, 5, 7, 8).
4. **The engine's code as a field.** `EngineCode` and `engine_code` in
   `dialects.py`; `classify_failure` and the exhausted-retry `conflict`
   carry `data["vfs.engine_error"]`. Add the per-leg fault objects of
   §8.1 to `tests/support/faults.py` (their first use) and the
   per-leg classification rows. Run the four engine legs (criterion 9).
5. **Durability from the live connection.** `durability_probe` on
   `DialectProfile`, the five probes of §2.5, `EngineHost.durability`
   read once at first touch, and `traits()` reporting it. Pin
   `InMemoryStorage` at `"none"`. Run the four engine legs
   (criterion 6).

## Slice E — the families (spec §7, §8, §9), with the retry counter

6. **The test support.** `tests/support/images.py` (`full_image`,
   `logical_image`, `LOGICAL_COLUMNS` and its drift test);
   `tests/support/access.py` (the statement meter on
   `before_cursor_execute`, the `CursorResult` fetch wrapper, the
   asyncpg `COPY` wrapper, `NativeMeter`), absorbing spec 178's
   counter if it landed; `tests/support/faults.py` (`EngineFaults`
   with `at(n, retryable=, times=)`, `FaultRecord`, `Crash`). Add the
   `faults`, `reopen` and `meter` fixtures to `contract/_base.py`
   (skipping by default) and provide them per leg in
   `test_conformance.py` (§6.3). Self-tests for each helper on SQLite.
7. **The retry counter.** `with_retry(fn, *, op)`, `RetryTally`,
   `EngineHost.retries`, and `DatabaseStorage.counters()` with its
   `retries` field (the `rights` field arrives in task 12). Tests on
   SQLite with the retryable fault (criterion 12).
8. **Family (a): the mixed batch.** `contract/atomicity.py` with every
   scenario of §7, the commit-event count, and the full image; the
   `slow` 10,000 + 1 variant; the `rmedge` warning row; the two-mount
   tear test beside the router tests. Run the four engine legs
   (criterion 16).
9. **Family (b): crash at each mutating statement.**
   `contract/crash.py` with §8.3's procedure for every whole-batch
   method of §3.1: the reference run on a sibling store, the fatal pass
   with `reopen` and the full image, the retryable pass with the
   logical image and the redrive count. Mark the family `slow`. Run the
   four engine legs (criterion 17).
10. **Family (b): every seam.** `SEAM_CLASSES` with all 21 seams, the
    parse-based drift test, the `Crash` handlers, the readers-exact
    checks at three authorities, the convergence checks, and the
    two lease variants for each `reindex` seam. Run the four engine
    legs (criterion 18).
11. **Family (c): the access-path tables.** `contract/access_paths.py`
    with the world and the cases of §9.2; the five fixture files,
    repinned on each leg (`VFS_ACCESS_PATHS_REPIN=1`, `-n 0`); the
    §9.5 dimension assertions; the router-adds-nothing check;
    `native.json` on the SQLite leg. The SQLite fixture reproduces
    §9.4. Run the four engine legs (criteria 19–21).

## Slice C — counters and the fold (spec §5)

12. **The rights-cache counts.** `RightsCacheCounts` and
    `RightsCache.counts()`, counted at `ids`, `get` and `put`; the
    `rights` field of `counters()`. Tests in
    `tests/storage/database/test_rights.py` (criterion 13). If Clay
    answers §5.4 "through the router", add the router method here.
13. **Fold the revalidation reads.** `stamps_and_marks` in `rights.py`
    and its use on both paths of `resolve_authority`; the
    one-chunk condition and the fallback. Repin the five access-path
    fixtures in the same commit and review the diff: every alice and
    anonymous row loses one statement, no system row changes. The
    forced-small-budget test. Run the four engine legs (criterion 14).

## Slice B — derived operations and the feature gate (spec §2.3, §4)

14. **The derived operations.** Lift the two row filters from
    `base.py` into `src/vfs/chain.py`. Add `src/vfs/derived.py` with
    `tree`, `copy`, `glob` and `grep` (§4.2), `DERIVED_READ_ROWS` and
    `DERIVED_READ_BYTES`. `MountMeta.caps` becomes declared plus
    derivable minus the mask; add `native_caps` and `MountInfo.derived`.
    `_call_storage` calls native or derived. Add a partial backend
    double to `tests/support/base_doubles.py` and the differential
    tests against `InMemoryStorage` (criterion 10).
15. **The feature gate.** The gate step in `_gate_entry`, the derive
    arms for `read_range` and `ls_cursor`, and the refusal with
    `data["vfs.feature"]`. Add each `FEATURE_ARGUMENTS` row with its
    owning spec (174, 176, 177, 178, 180), whichever has landed; the
    rest join when they land. Add the derived `edit` once 174's
    `if_versions` exists, with its rival case (criteria 10, 11).

## Docs

16. **Docs.** `docs/explanation/write-pipeline.md` (the atomic unit,
    the two models, the cross-mount tear), `docs/contributing.md` (the
    protocol families and the contract package),
    `docs/reference/glossary.md` (feature, trait, atomic unit, access
    path, derived operation), and the README banner's `SupportsRun`
    sentence if spec 167 has not removed it. Fill in the spec's
    landing notes, and move the spec to `archive/` when every
    criterion holds (criteria 22, 23 checked across all tasks).
