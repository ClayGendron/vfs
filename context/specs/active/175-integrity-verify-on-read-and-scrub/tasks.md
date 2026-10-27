# 175 — tasks

Four slices, landing in order: A, then B and C (independent of each
other, both need A), then D (needs B and spec 176's resumption key on
`Result`). Every task lands green through `scripts/ci.sh` (lint,
format, types, 100% coverage). B, C and D also run the four real-engine
legs (the `db_test` skill) before they land. Counts, never clocks.

## Slice A — the hash law, the offload rule, the kind (spec §1, §2)

1. **One hash.** Add `content_digest` to `models/version.py`; route
   `measure_text`, `measure_bytes` and `Version.reconstruct` through
   it; export it from `vfs.models`. Pin criterion 1.
2. **The threshold's home.** Move `MEASURE_OFFLOAD_BYTES` from
   `base.py` to `models/version.py`, export it, import it in
   `base.py`. `ba77449`'s pins pass unchanged (criterion 2).
3. **`measure_all`.** Add it to `storage/backends/database/offload.py`
   with the per-call rule (inline under the threshold, a hop per
   `BLOB_PAGE_BYTES` page above it, gathered, in order). Update the
   module docstring's list of deliberate threads. Pin criterion 3 by
   spying `call_offloaded`.
4. **The kind.** Add `ErrorKind.integrity = "vfs.unavailable.integrity"`
   with its `KindContract` (retry class `never`) and its `data` record
   in the `ErrorKind` docstring. Pin criterion 4. Resolve the §2
   marker with Clay first; if he picks plain `unavailable`, this task
   shrinks to the docstring's `data` record.

## Slice B — verify on read (spec §3)

5. **The integrity module.** Add
   `storage/backends/database/integrity.py` with `BodyCheck` (the
   suspects set, `screen`, the `read:suspect` seam, the
   `StaleSnapshot` raise, the error constructor with the fixed
   details). Unit-test the confirm law on plain mappings.
6. **The read path.** `read_rows` fetches `content_hash` and `source`
   beside a body and observes with the `served` mask; `_point_rows`
   collects, screens and then observes; `DatabaseStorage.read` mints
   one `BodyCheck` per call over `host.offload_executor`. Refusals for
   kind and permission stay ahead of the check. Update the
   `SupportsRead` and `DatabaseStorage` docstrings (§3.7).
7. **The integrity contract.** Add
   `tests/support/integrity_contract.py` (`IntegrityContract` with the
   five planters and the statement and hop counters) and mix it into
   all six conformance classes. Pin criteria 5–12.
8. **Bytes in hand on SQLite.** Where `content_bytes` is declared, the
   read selects the text body as bytes, hashes, then decodes once.
   Pin criterion 13. Run the four engine legs; land slice B.

## Slice C — the write side (spec §4)

9. **`content_hash` on written rows.** `_finish`'s staged branch and
   `final_rows`/`observe_final` carry it. Pin criterion 14, including
   the unchanged create and update statement counts.
10. **The snapshot's recorded hash.** `_fetch_committed` selects
    `content_hash`; `StagedEntry` gains `base_content_hash` and
    `base_metrics`; `stage_update` copies the hash.
11. **The edit.** Split `edited_entry` into `edited_text` and
    `edited_entry(..., measured=)`; `edit_rows` checks pre-images
    (missing, unhashed, mismatch), applies, then measures final texts
    with `measure_all` and validates through `MEASURED_BODY`;
    `DatabaseStorage.edit` passes the executor and holds the suspects
    for the confirm redrive. Pin criteria 15 and 16.
12. **The mint.** `mint_versions` and `_mint_rows` measure pre-images
    with `measure_all`, reuse `base_metrics` for held rows, store the
    recorded hash when it disagrees with the body, and return the
    warning, which `_finish` attaches. Thread `executor` through
    `write_rows`, `_finish` and `_apply`. Update the `versions.py`
    docstring. Resolve the §4.4 marker with Clay first. Pin criterion
    17. Run the four engine legs; land slice C.

## Slice D — `scrub` (spec §5)

13. **Vocabulary and surface.** `"scrub"` in `Op`, `READ_OPS`,
    `DEVELOPER_OPS` and `VERB_RUNGS` (`read`); `SCRUB_LIMIT_DEFAULT`;
    the `deny_ops` guard exempts developer ops; the `params.py` row;
    `_DEFAULT_PROJECTION`; `SupportsScrub` and its `_FAMILY_OPS` row;
    the router method, its `_call_storage` arm and the `Session`
    method. The drift tests (`test_ops.py`, `test_params.py`, the
    protocol tests) pass with `scrub` registered.
14. **The walk.** `scrub_page` builders in `integrity.py`: the bodies
    and versions metadata statements, the byte-paged body pieces
    (membership chunks for bodies, arm-budget OR-fans for versions),
    the hashes through `measure_all`, the confirm session, the
    resumption key on spec 176's `Result` field, the `scrub` extra and
    the warnings. `DatabaseStorage.scrub` with its gate. Pin criteria
    18–20 in `IntegrityContract`.
15. **Docs.** Add `scrub` to the reference docs beside `sweep`
    (developer plane; report-only; pacing is the caller's), and the
    `integrity` kind to the error reference. Run the four engine legs;
    land slice D. Fold the ADR amendments and rebase notes (spec
    "ADR amendments" and "Rebase notes") into ADR 087 and specs 167,
    171, 172, 176, 178 and 180, and move this spec to `archive/`.
